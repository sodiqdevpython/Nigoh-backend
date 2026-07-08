"""
Nigoh Agent'ning shifrlangan result.log faylini backend'da ochish.
Format va kalit Nigoh/Utils/LogCrypto.cs bilan bir xil:
  key    = SHA256(b"sodiq2005.py")            → 32 bayt
  line   = Base64( IV[16] || AES_CBC(cipher) )
  padding = PKCS7
"""
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

MASTER_PASSWORD = b"sodiq2005.py"
_KEY = hashlib.sha256(MASTER_PASSWORD).digest()


def decrypt_line(b64_line: str) -> str:
    """Bitta shifrlangan qatorni oddiy matnga o'giradi. Xatolik bo'lsa qatorni o'zi qaytaradi."""
    b64_line = (b64_line or "").strip()
    if not b64_line:
        return ""
    try:
        data = base64.b64decode(b64_line)
        if len(data) < 32:
            return b64_line
        iv, cipher_bytes = data[:16], data[16:]

        cipher = Cipher(algorithms.AES(_KEY), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(cipher_bytes) + decryptor.finalize()

        unpadder = PKCS7(128).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
        return plain.decode("utf-8", errors="replace")
    except Exception:
        return b64_line  # Base64 emas yoki xato — o'sha holida


def decrypt_bytes(raw: bytes) -> str:
    """Butun log fayl mazmunini (bytes) oddiy matn (str) qilib qaytaradi."""
    text = raw.decode("utf-8", errors="replace")
    lines = text.replace("\r\n", "\n").split("\n")
    return "\n".join(decrypt_line(l) for l in lines)
