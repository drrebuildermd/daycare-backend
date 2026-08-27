"""EAS 로 빌드한 APK 에서 카카오용 키 해시를 뽑는다.

카카오 안드로이드 플랫폼에 등록할 '키 해시' 는
    base64( SHA1( 서명 인증서 DER ) )
이다.

EAS 는 키스토어를 Expo 서버에 보관하므로 로컬에 keystore 파일이 없고,
이 환경에는 keytool 도 없다. 그래서 실제로 배포된 APK 에서 인증서를 꺼낸다.
그 값이 곧 그 APK 를 설치한 폰에서 카카오가 검사하는 값이라, 가장 확실하다.

요즘 APK 는 v1(JAR, META-INF/*.RSA) 서명 없이 v2/v3 만 쓰는 경우가 많다.
그때는 'APK Signing Block' 을 직접 읽어야 한다. 아래가 그 파서다.

사용: .venv\\Scripts\\python.exe -X utf8 tools_key_hash.py <APK_URL 또는 로컬경로>
"""
import base64
import hashlib
import io
import struct
import sys

import httpx
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import load_der_x509_certificate

MAGIC = b"APK Sig Block 42"
V2_ID = 0x7109871A
V3_ID = 0xF05368C0
V31_ID = 0x1B93AD61


def load_apk(source: str) -> bytes:
    if source.startswith("http"):
        print(f"APK 내려받는 중… {source[:70]}")
        with httpx.Client(timeout=600.0, follow_redirects=True) as client:
            response = client.get(source)
        response.raise_for_status()
        return response.content
    return io.open(source, "rb").read()


def find_central_directory_offset(data: bytes) -> int:
    """EOCD(끝 중앙 디렉터리 레코드)에서 중앙 디렉터리 시작 위치를 읽는다."""
    # EOCD 는 파일 끝에서 최대 64KB 안에 있다. 뒤에서부터 시그니처를 찾는다.
    tail = data[-(65536 + 22):]
    index = tail.rfind(b"PK\x05\x06")
    if index < 0:
        raise ValueError("EOCD 를 찾지 못했습니다. 올바른 APK 가 아닙니다.")
    eocd = tail[index:]
    return struct.unpack_from("<I", eocd, 16)[0]


def read_signing_block(data: bytes) -> dict[int, bytes]:
    """APK Signing Block 을 id -> value 로 읽는다."""
    cd_offset = find_central_directory_offset(data)
    if data[cd_offset - 16:cd_offset] != MAGIC:
        raise ValueError("APK Signing Block 이 없습니다. (v1 서명만 있는 APK)")

    size_at_end = struct.unpack_from("<Q", data, cd_offset - 24)[0]
    block_start = cd_offset - size_at_end - 8

    pairs: dict[int, bytes] = {}
    cursor = block_start + 8
    limit = cd_offset - 24
    while cursor < limit:
        pair_len = struct.unpack_from("<Q", data, cursor)[0]
        if pair_len < 4 or cursor + 8 + pair_len > cd_offset:
            break
        pair_id = struct.unpack_from("<I", data, cursor + 8)[0]
        pairs[pair_id] = data[cursor + 12:cursor + 8 + pair_len]
        cursor += 8 + pair_len
    return pairs


def read_length_prefixed(buffer: bytes, offset: int) -> tuple[bytes, int]:
    length = struct.unpack_from("<I", buffer, offset)[0]
    start = offset + 4
    return buffer[start:start + length], start + length


def certificates_from_signer_block(block: bytes) -> list[bytes]:
    """v2/v3 서명자 블록에서 인증서 DER 들을 꺼낸다.

    구조(공통 앞부분):
      signers            : length-prefixed sequence
        signer           : length-prefixed
          signed data    : length-prefixed
            digests      : length-prefixed sequence
            certificates : length-prefixed sequence of length-prefixed DER
    """
    certs: list[bytes] = []
    signers, _ = read_length_prefixed(block, 0)

    cursor = 0
    while cursor < len(signers):
        signer, cursor = read_length_prefixed(signers, cursor)
        try:
            signed_data, _ = read_length_prefixed(signer, 0)
            # digests 를 건너뛰고 certificates 로 간다.
            _digests, next_offset = read_length_prefixed(signed_data, 0)
            cert_seq, _ = read_length_prefixed(signed_data, next_offset)
            inner = 0
            while inner < len(cert_seq):
                der, inner = read_length_prefixed(cert_seq, inner)
                if der:
                    certs.append(der)
        except (struct.error, IndexError):
            continue
    return certs


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    data = load_apk(sys.argv[1])
    print(f"APK 크기: {len(data) / 1024 / 1024:.1f} MB")

    try:
        pairs = read_signing_block(data)
    except ValueError as error:
        print(f"실패: {error}")
        return 1

    found = {V2_ID: "v2", V3_ID: "v3", V31_ID: "v3.1"}
    present = [name for pid, name in found.items() if pid in pairs]
    print(f"서명 스킴: {', '.join(present) if present else '없음'}\n")

    seen: set[str] = set()
    for pid, label in found.items():
        if pid not in pairs:
            continue
        for der in certificates_from_signer_block(pairs[pid]):
            sha1 = hashlib.sha1(der).digest()
            key_hash = base64.b64encode(sha1).decode()
            if key_hash in seen:
                continue
            seen.add(key_hash)

            cert = load_der_x509_certificate(der)
            assert cert.public_bytes(Encoding.DER) == der

            print("=" * 66)
            print(f"  서명 스킴 : {label}")
            print(f"  발급 대상 : {cert.subject.rfc4514_string()}")
            print(f"  유효 기간 : {cert.not_valid_before_utc:%Y-%m-%d} ~ "
                  f"{cert.not_valid_after_utc:%Y-%m-%d}")
            print(f"  SHA-1     : {sha1.hex().upper()}")
            print()
            print(f"  ★ 카카오에 등록할 키 해시 : {key_hash}")
            print("=" * 66)
            print()

    if not seen:
        print("인증서를 하나도 읽지 못했습니다.")
        return 1

    print("등록 위치: Kakao Developers > 내 애플리케이션 > 앱 설정 > 플랫폼 > Android")
    print("  패키지명 : com.daycare.routing")
    print("  키 해시  : 위 값")
    return 0


if __name__ == "__main__":
    sys.exit(main())
