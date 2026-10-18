"""Synthetic encrypted SQLite/WAL regression adapted from QJQ; no personal data."""
import ctypes, hashlib, hmac, os, sqlite3, struct, sys, threading, time
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox
module=load('group-messages')
wechat=module.wechat
crypto=sys.modules[module.__name__+'.native.crypto']
AESCBC,checksum,mac_key=crypto.AESCBC,crypto.checksum,crypto.mac_key
KEY,SALT=bytes(range(32)),bytes(range(16))
def encrypted_page(page: bytes, number: int, cipher: AESCBC) -> bytes:
    start = 16 if number == 1 else 0
    iv = os.urandom(16)
    payload = page[start:4016]
    output = ctypes.create_string_buffer(len(payload))
    vector = ctypes.create_string_buffer(iv, 16)
    length = ctypes.c_ulong()
    cipher.lib.BCryptEncrypt.argtypes = cipher.lib.BCryptDecrypt.argtypes
    result = cipher.lib.BCryptEncrypt(
        cipher.key,
        payload,
        len(payload),
        None,
        vector,
        16,
        output,
        len(output),
        ctypes.byref(length),
        0,
    )
    assert result == 0
    raw = output.raw[: length.value] + iv
    return (
        (SALT if number == 1 else b"")
        + raw
        + hmac.digest(mac_key(KEY, SALT), raw + struct.pack("<I", number), "sha512")
    )

def encrypted_fixture(path: Path, initial_sql: str, wal_sql: str = "") -> None:
    """Create real reserved-space SQLite pages, then encrypt them and WAL frames."""
    library_path = Path(sys.base_prefix) / "DLLs/sqlite3.dll"
    if os.name != "nt" or not library_path.exists():
        raise RuntimeError("Windows CNG + bundled SQLite fixture required")
    path.parent.mkdir(parents=True, exist_ok=True)
    plaintext = path.with_suffix(".fixture")
    lib = ctypes.CDLL(str(library_path))
    db = ctypes.c_void_p()
    lib.sqlite3_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
    lib.sqlite3_file_control.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_void_p,
    ]
    lib.sqlite3_exec.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    lib.sqlite3_close.argtypes = [ctypes.c_void_p]
    assert lib.sqlite3_open(str(plaintext).encode("utf-8"), ctypes.byref(db)) == 0
    try:
        reserve = ctypes.c_int(80)
        assert lib.sqlite3_file_control(db, b"main", 38, ctypes.byref(reserve)) == 0

        def sql(value: str) -> None:
            assert lib.sqlite3_exec(db, value.encode("utf-8"), None, None, None) == 0

        sql(
            "PRAGMA page_size=4096; PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0;"
            + initial_sql
        )
        sql("PRAGMA wal_checkpoint(TRUNCATE);")
        if wal_sql:
            sql(wal_sql)
        with closing(AESCBC(KEY)) as cipher:
            plain = plaintext.read_bytes()
            assert plain[20] == 80 and len(plain) % 4096 == 0
            path.write_bytes(
                b"".join(
                    encrypted_page(
                        plain[offset : offset + 4096], offset // 4096 + 1, cipher
                    )
                    for offset in range(0, len(plain), 4096)
                )
            )
            if wal_sql:
                wal = plaintext.with_name(plaintext.name + "-wal").read_bytes()
                header = wal[:32]
                magic = struct.unpack(">I", header[:4])[0]
                endian = "<" if magic == 0x377F0682 else ">"
                rolling = checksum(header[:24], endian)
                result = bytearray(header[:24] + struct.pack(">II", *rolling))
                for offset in range(32, len(wal), 4120):
                    frame = wal[offset : offset + 24]
                    number = struct.unpack(">I", frame[:4])[0]
                    content = encrypted_page(
                        wal[offset + 24 : offset + 4120], number, cipher
                    )
                    rolling = checksum(frame[:8] + content, endian, rolling)
                    result.extend(frame[:16] + struct.pack(">II", *rolling) + content)
                path.with_name(path.name + "-wal").write_bytes(result)
    finally:
        lib.sqlite3_close(db)
        plaintext.unlink(missing_ok=True)
def check():
    if os.name!='nt':
        print('SKIP: Windows native CNG regression');return
    with sandbox('group-native') as context:
        root=context.data_dir/'account/db_storage'
        group,private='synthetic-course@chatroom','synthetic-private'
        table='Msg_'+hashlib.md5(group.encode()).hexdigest()
        personal='Msg_'+hashlib.md5(private.encode()).hexdigest()
        schema='local_id INTEGER,server_id INTEGER,local_type INTEGER,real_sender_id INTEGER,create_time INTEGER,WCDB_CT_message_content INTEGER,message_content TEXT,compress_content BLOB'
        now=int(time.time())
        encrypted_fixture(root/'message/message_0.db',
            f"CREATE TABLE Name2Id(user_name TEXT); INSERT INTO Name2Id VALUES('{group}'),('synthetic-teacher'),('{private}'); CREATE TABLE {table}({schema}); INSERT INTO {table} VALUES(1,10,1,2,{now-6*86400},0,'六天前的课程消息',NULL); CREATE TABLE {personal}({schema}); INSERT INTO {personal} VALUES(1,99,1,2,{now},0,'private text excluded',NULL);",
            f"INSERT INTO {table} VALUES(2,11,1,2,{now},0,'最新 WAL 消息',NULL);")
        encrypted_fixture(root/'contact/contact.db',f"CREATE TABLE contact(username TEXT,remark TEXT,nick_name TEXT); INSERT INTO contact VALUES('{group}','','合成课程群'),('synthetic-teacher','','合成老师'),('{private}','','private person');")
        keys={'message/message_0.db':KEY.hex(),'contact/contact.db':KEY.hex()}
        cancel=threading.Event();storage=context.data_dir/'output'
        source=root/'message/message_0.db'
        original=(source.stat().st_mtime_ns,source.with_name(source.name+'-wal').stat().st_mtime_ns)
        discovery=wechat.build_snapshot(root,keys,None,7,cancel,lambda *a:None,storage)
        assert discovery['snapshot'] is None and discovery['groups'][0]['name']=='合成课程群'
        report=wechat.build_snapshot(root,keys,{group},7,cancel,lambda *a:None,storage)
        assert report['wal_commits']>=1
        output=Path(report['snapshot'])
        messages=wechat.scan(output,[group],7,cancel)[group]
        assert [row['text'] for row in messages]==['六天前的课程消息','最新 WAL 消息']
        assert messages[0]['sender_name']=='合成老师'
        assert wechat.scan(output,[],7,cancel)=={}
        with closing(sqlite3.connect(output/'message/message_0.db')) as db:
            assert personal not in {row[0] for row in db.execute("SELECT name FROM sqlite_master")}
        with closing(sqlite3.connect(output/'contact/contact.db')) as db:
            assert private not in {row[0] for row in db.execute('SELECT username FROM contact')}
        assert original==(source.stat().st_mtime_ns,source.with_name(source.name+'-wal').stat().st_mtime_ns)
        # A changed client pauses first, probes only existing keys, and never publishes its candidate.
        client=SimpleNamespace(version='4.1.new',executable='C:/fixture/Weixin.exe')
        paused=[]
        config={'mode':'native','selected':[{'id':group}],'approved_version':'4.1.old','history_days':7,'snapshot':str(output)}
        with patch.object(wechat.version,'observe_version',return_value=client):
            try:wechat.synchronize(config,{'database_dir':str(root),'keys':keys},storage,cancel,lambda *a:None,pause_for_version=lambda value:paused.append(value.version))
            except wechat.VersionChanged as error:assert error.compatible
            else:raise AssertionError('Version change did not pause')
        assert paused==['4.1.new'] and output.exists() and len(list((storage/'snapshots').iterdir()))==1
        cancel.set()
        try:wechat.build_snapshot(root,keys,{group},7,cancel,lambda *a:None,storage)
        except crypto.NativeError:pass
        else:raise AssertionError('Cancellation ignored')
        assert output.exists()
        # Authenticate every encrypted page: corruption must not replace the last good snapshot.
        cancel.clear()
        with source.open('r+b') as file:
            file.seek(100);file.write(b'corrupt-page')
        try:wechat.build_snapshot(root,keys,{group},7,cancel,lambda *a:None,storage)
        except crypto.NativeError:pass
        else:raise AssertionError('Unauthenticated page accepted')
        assert output.exists() and not list((storage/'work').iterdir())
    print('PASS: encrypted committed WAL, selected groups only, seven-day scope, sender names, source read-only, version pause, cancellation and integrity failure cleanup')

if __name__=='__main__':check()
