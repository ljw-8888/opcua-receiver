import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import socket
import tempfile
import unittest
from unittest.mock import patch

from asyncua import ua, Server
from openpyxl import load_workbook

from telemetry import (ExcelRecorder, Receiver, Simulator, endpoint, load_tags, simulated_values,
                       NAMESPACE, HEARTBEAT, validate_endpoint, parse_address, address_key,
                       validate_security, excel_value, save_setup, load_setup)


class DataTests(unittest.TestCase):
    def test_spreadsheet_relations_and_ranges(self):
        tags = load_tags()
        self.assertEqual(len(tags), 112)
        rng = random.Random(42)
        for _ in range(20):
            values = simulated_values(tags, 30, rng)
            self.assertEqual(len(values), 112)
            for tag in tags:
                key = tag['identifier']
                if tag['metric'] == 'VaporFraction':
                    self.assertGreaterEqual(values[key], 0)
                    self.assertLessEqual(values[key], 1)
                    self.assertAlmostEqual(values[key] + values[key.replace('VaporFraction', 'LiquidFraction')], 1)
                if tag['metric'] == 'Velocity':
                    self.assertGreaterEqual(values[key], 0)

    def test_private_endpoint(self):
        self.assertEqual(endpoint('192.168.1.10', 4840), 'opc.tcp://192.168.1.10:4840/hd/')
        with self.assertRaises(ValueError):
            endpoint('8.8.8.8', 4840)

    def test_bad_quality_is_not_a_valid_number(self):
        receiver = Receiver()
        receiver.selected = {'Stream/1/Temperature'}
        receiver.accept('Stream/1/Temperature', ua.DataValue(
            Value=ua.Variant(42.0, ua.VariantType.Double),
            StatusCode=ua.StatusCode(ua.StatusCodes.BadNoCommunication),
            SourceTimestamp=datetime.now(timezone.utc),
        ))
        sample = receiver.samples['Stream/1/Temperature']
        self.assertIsNone(sample['value'])
        self.assertEqual(sample['raw_value'], 42)
        self.assertEqual(sample['quality'], 'BadNoCommunication')

    def test_generic_addresses_security_and_excel_types(self):
        for url in ['opc.tcp://plant-host:49320/vendor/path', 'opc.tcp://[::1]:4840/']:
            self.assertEqual(validate_endpoint(url), url)
        for url in ['http://localhost:4840/', 'opc.tcp://user:secret@host:4840', 'opc.tcp://host:0/', 'opc.tcp://host:4840/?x=1']:
            with self.assertRaises(ValueError):
                validate_endpoint(url)
        self.assertEqual(parse_address('i=123', 'urn:plant')[1], 'urn:plant')
        self.assertEqual(parse_address('ns=0;i=85', 'urn:plant')[1], '')
        self.assertEqual(parse_address('s=Tag;part=1', 'urn:plant')[0].Identifier, 'Tag;part=1')
        for text in ['raw-tag', 'i=-1', 'ns=70000;i=1', 'g=broken']:
            with self.assertRaises(ValueError):
                parse_address(text)
        with self.assertRaises(ValueError):
            validate_security({'username': 'operator', 'password': 'secret'})
        self.assertEqual(excel_value(2**63+1), str(2**63+1))
        self.assertEqual(excel_value(b'abc'), 'base64:YWJj')
        self.assertIn('+00:00', excel_value(datetime.now(timezone.utc)))
        self.assertEqual(excel_value('A\x00B'), 'A\\u0000B')
        with self.assertRaises(ValueError):
            excel_value('x'*32768)


async def until(predicate, timeout=15):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.1)


class CommunicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_subscribe_stale_reconnect_and_excel(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        server = Simulator()
        receiver = Receiver()
        with tempfile.TemporaryDirectory() as directory:
            recorder = ExcelRecorder(directory)
            try:
                server.start('127.0.0.1', port, 0.2, 5)
                await until(lambda: server.state == 'Running')
                receiver.set_heartbeat('s='+HEARTBEAT, NAMESPACE, 0.6)
                receiver.connect(endpoint('127.0.0.1', port))
                await until(lambda: receiver.state == 'Connected')
                await receiver.browse('s=Telemetry', NAMESPACE)
                self.assertEqual(len(receiver.tags), 113)
                identifiers = ['Stream/1/Temperature', 'Stream/1/Pressure', 'Equipment/V-102/LevelM']
                keys = [address_key(NAMESPACE, 's='+key) for key in identifiers]
                receiver.select(keys)
                await until(lambda: len(receiver.samples) == 3 and receiver.subscription_count == 3)
                self.assertTrue(all(s['quality'] == 'Good' for s in receiver.samples.values()))
                node = receiver.client.get_node(ua.NodeId(identifiers[0], receiver.namespaces.index(NAMESPACE)))
                with self.assertRaises(ua.UaStatusCodeError):
                    await node.write_value(42.0)
                recorder.start(receiver, 'samples.xlsx', 0.2)
                await until(lambda: recorder.rows >= 6)
                await recorder.stop()
                path = Path(directory) / 'samples.xlsx'
                workbook = load_workbook(path, read_only=True, data_only=True)
                self.assertEqual(workbook.active.max_row, recorder.rows + 1)
                workbook.close()
                with self.assertRaises(ValueError):
                    recorder.start(receiver, 'samples.xlsx', 1)
                with self.assertRaises(ValueError):
                    recorder.start(receiver, '../outside.xlsx', 1)
                before = path.read_bytes()
                row = receiver.snapshot()[0]
                row['asset'] = '=1+1'
                with patch('telemetry.os.replace', side_effect=PermissionError('locked')):
                    with self.assertRaises(PermissionError):
                        recorder._save([row])
                self.assertEqual(path.read_bytes(), before)
                self.assertTrue(path.with_suffix('.pending.xlsx').exists())
                recorder._save([])
                workbook = load_workbook(path, data_only=False)
                self.assertEqual(workbook.active.cell(workbook.active.max_row, 3).data_type, 's')
                workbook.close()
                receiver.stale_seconds = 0.6
                server.paused = True
                await until(lambda: receiver.freshness == 'Stale')
                self.assertEqual(receiver.state, 'Connected')
                server.paused = False
                await until(lambda: receiver.freshness == 'Fresh')
                await server.stop()
                await until(lambda: receiver.state != 'Connected')
                server.start('127.0.0.1', port, 0.2, 5)
                await until(lambda: receiver.connections >= 2 and receiver.subscription_count == 3)
                await until(lambda: len(receiver.samples) == 3)
            finally:
                await recorder.stop()
                await receiver.disconnect()
                await server.stop()


class GenericServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_encrypted_username_login_and_certificate_rejection(self):
        import ipaddress
        from datetime import timedelta
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from asyncua.server.user_managers import User, UserRole

        class Users:
            def get_user(self, iserver, username=None, password=None, certificate=None):
                return User(role=UserRole.User) if (username, password)==('test-operator', 'test-only-password') else None

        with tempfile.TemporaryDirectory() as directory:
            def certificate(name):
                key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
                now = datetime.now(timezone.utc)
                cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                        .public_key(key.public_key()).serial_number(x509.random_serial_number())
                        .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
                        .add_extension(x509.SubjectAlternativeName([x509.UniformResourceIdentifier('urn:test:'+name),
                             x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
                        .sign(key, hashes.SHA256()))
                cp = Path(directory)/(name+'.der')
                kp = Path(directory)/(name+'.pem')
                cp.write_bytes(cert.public_bytes(serialization.Encoding.DER))
                kp.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
                kp.chmod(0o600)
                return str(cp), str(kp)
            server_cert, server_key = certificate('server')
            client_cert, client_key = certificate('client')
            wrong_cert, _ = certificate('wrong-server')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            server = Server(user_manager=Users())
            await server.init()
            await server.set_application_uri('urn:test:server')
            url = f'opc.tcp://127.0.0.1:{port}/secure/'
            server.set_endpoint(url)
            await server.load_certificate(server_cert)
            await server.load_private_key(server_key)
            server.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
            server.set_identity_tokens([ua.UserNameIdentityToken])
            ns = await server.register_namespace('urn:secure:plant')
            await server.nodes.objects.add_variable(ua.NodeId(9001, ns), 'Temperature', 42.0)
            await server.start()
            receiver = Receiver()
            options = {'mode':'Basic256Sha256 / SignAndEncrypt', 'certificate':client_cert,
                       'private_key':client_key, 'server_certificate':server_cert,
                       'application_uri':'urn:test:client', 'username':'test-operator', 'password':'test-only-password'}
            try:
                receiver.connect(url, options)
                await until(lambda: receiver.state=='Connected')
                key = await receiver.add_node('i=9001', 'urn:secure:plant')
                receiver.select([key])
                await until(lambda: key in receiver.samples)
                self.assertEqual(receiver.samples[key]['value'], 42.0)
                await receiver.disconnect()
                receiver.connect(url, dict(options, password='incorrect'))
                await until(lambda: bool(receiver.error))
                self.assertNotEqual(receiver.state, 'Connected')
                await receiver.disconnect()
                receiver.connect(url, dict(options, server_certificate=wrong_cert))
                await until(lambda: bool(receiver.error))
                self.assertNotEqual(receiver.state, 'Connected')
            finally:
                await receiver.disconnect()
                await server.stop()

    async def test_no_heartbeat_mixed_types_namespace_remap_and_profile(self):
        import uuid
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        url = f'opc.tcp://127.0.0.1:{port}/vendor/arbitrary/'
        guid = uuid.UUID('12345678-1234-1234-1234-123456789abc')

        async def start_server(extra=False):
            server = Server()
            await server.init()
            server.set_endpoint(url)
            if extra:
                await server.register_namespace('urn:unrelated:new')
            ns = await server.register_namespace('urn:plant:a')
            ns2 = await server.register_namespace('urn:plant:b')
            folder = await server.nodes.objects.add_object(ua.NodeId(500, ns), 'Plant')
            nodes = []
            definitions = [(101, ns, 'Pressure', ua.Variant(3.25, ua.VariantType.Float)),
                           (101, ns2, 'Running', ua.Variant(True, ua.VariantType.Boolean)),
                           ('Batch', ns, 'Batch', ua.Variant(2**63+1, ua.VariantType.UInt64)),
                           (guid, ns, 'GuidTag', ua.Variant('=test', ua.VariantType.String)),
                           (b'node', ns, 'ByteTag', ua.Variant(datetime.now(timezone.utc), ua.VariantType.DateTime))]
            for identifier, namespace, name, value in definitions:
                nodes.append(await folder.add_variable(ua.NodeId(identifier, namespace), name, value))
            await server.start()
            return server, ns, nodes

        server, original_ns, nodes = await start_server()
        receiver = Receiver()
        with tempfile.TemporaryDirectory() as directory:
            recorder = ExcelRecorder(directory)
            try:
                receiver.connect(url)
                await until(lambda: receiver.state == 'Connected')
                await receiver.browse('ns=0;i=85')
                self.assertTrue(any(f['name']=='Plant' for f in receiver.folders))
                await receiver.browse('i=500', 'urn:plant:a')
                self.assertEqual(len(receiver.tags), 5)
                pressure_key = await receiver.add_node('i=101', 'urn:plant:a', 'Configured pressure', 'kPa')
                await receiver.browse('i=500', 'urn:plant:a')
                pressure_tag = next(t for t in receiver.tags if t['identifier']==pressure_key)
                self.assertEqual((pressure_tag['metric'], pressure_tag['unit']), ('Configured pressure', 'kPa'))
                keys = [tag['identifier'] for tag in receiver.tags]
                receiver.select(keys)
                # The first data-change batch can arrive before all handles are counted.
                await until(lambda: len(receiver.samples) == 5 and receiver.subscription_count == 5)
                receiver.stale_seconds = 0.2
                await asyncio.sleep(0.5)
                self.assertEqual(receiver.freshness, 'Not monitored')
                self.assertEqual(receiver.state, 'Connected')
                self.assertEqual(receiver.samples[address_key('urn:plant:a', 'i=101')]['value'], 3.25)
                self.assertIs(receiver.samples[address_key('urn:plant:b', 'i=101')]['value'], True)
                await nodes[0].write_value(ua.Variant(7.5, ua.VariantType.Float))
                await until(lambda: receiver.samples[address_key('urn:plant:a', 'i=101')]['value']==7.5)
                profile = Path(directory)/'setup.json'
                save_setup({'endpoint':url, 'namespace':'urn:plant:a', 'root':'i=500', 'password':'DO_NOT_STORE', 'key_password':'PRIVATE'}, 0, receiver.tags, receiver.selected, profile)
                raw = profile.read_text()
                self.assertNotIn('DO_NOT_STORE', raw)
                self.assertNotIn('PRIVATE', raw)
                self.assertEqual(len(load_setup(profile)['tags']), 5)
                recorder.start(receiver, 'generic.xlsx', 0.2)
                await until(lambda: recorder.rows>=10)
                await recorder.stop()
                wb = load_workbook(Path(directory)/'generic.xlsx', data_only=False)
                rows = list(wb.active.values)[1:]
                self.assertTrue(all(row[1]==url and row[14]=='Not monitored' for row in rows))
                self.assertTrue(any(row[5]==str(2**63+1) for row in rows))
                self.assertTrue(any(row[5]=='=test' for row in rows))
                wb.close()
                receiver.set_heartbeat('i=999999', 'urn:plant:a', 0.2)
                await until(lambda: receiver.freshness=='Heartbeat unavailable')
                self.assertEqual(receiver.subscription_count, 5)
                receiver.set_heartbeat('')
                await server.stop()
                await until(lambda: receiver.state != 'Connected')
                server, new_ns, nodes = await start_server(extra=True)
                self.assertNotEqual(original_ns, new_ns)
                await until(lambda: receiver.connections>=2 and receiver.subscription_count==5)
                await until(lambda: len(receiver.samples)==5)
                self.assertTrue(all(s['quality']=='Good' for s in receiver.samples.values()))
                receiver.select(keys[:-1])
                await until(lambda: receiver.subscription_count==4)
                await server.delete_nodes([nodes[-1]])
                receiver.select(keys)
                await until(lambda: any(s['quality']=='BadNodeIdUnknown' for s in receiver.samples.values()))
                self.assertEqual(receiver.state, 'Connected')
                bad = [s for s in receiver.samples.values() if s['quality']=='BadNodeIdUnknown']
                self.assertEqual(len(bad), 1)
                self.assertIsNone(bad[0]['value'])
                with self.assertRaises(ValueError):
                    await receiver.add_node('i=123', 'urn:missing')
            finally:
                await recorder.stop()
                await receiver.disconnect()
                await server.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
