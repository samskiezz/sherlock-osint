"""Known-key authenticated encryption experiments. No key cracking or persisted keys."""

import base64
import hashlib
import json
import os
import cryptography
from cryptography.hazmat.primitives.ciphers.aead import (
    AESGCM,
    AESCCM,
    AESSIV,
    AESGCMSIV,
    ChaCha20Poly1305,
)
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import BaseModel, Field, SecretStr

ALGORITHMS = {
    "aes_gcm": "AES-GCM",
    "aes_ccm": "AES-CCM",
    "aes_gcm_siv": "AES-GCM-SIV",
    "aes_siv": "AES-SIV",
    "chacha20_poly1305": "ChaCha20-Poly1305",
    "fernet": "Fernet (AES-128-CBC + HMAC-SHA256)",
}


def operate(algorithm, operation, key, data, nonce=None, aad=b""):
    if algorithm not in ALGORITHMS or operation not in ("encrypt", "decrypt"):
        raise ValueError("Select a supported algorithm and encrypt/decrypt")
    if algorithm == "fernet":
        tool = Fernet(base64.urlsafe_b64encode(key))
        return getattr(tool, operation)(data), None
    if algorithm == "aes_siv":
        tool = AESSIV(key)
        return getattr(tool, operation)(data, [aad]), None
    nonce = (
        os.urandom(13 if algorithm == "aes_ccm" else 12)
        if operation == "encrypt"
        else nonce
    )
    expected = 13 if algorithm == "aes_ccm" else 12
    if nonce is None or len(nonce) != expected:
        raise ValueError(
            f"Nonce must contain {expected} bytes for this workbench format"
        )
    tool = {
        "aes_gcm": AESGCM,
        "aes_ccm": AESCCM,
        "aes_gcm_siv": AESGCMSIV,
        "chacha20_poly1305": ChaCha20Poly1305,
    }[algorithm](key)
    return getattr(tool, operation)(nonce, data, aad), nonce


def install(core):
    core.execute(
        "CREATE TABLE IF NOT EXISTS crypto_records(id TEXT PRIMARY KEY,created TEXT,data TEXT)"
    )

    class Experiment(BaseModel):
        algorithm: str
        operation: str = "decrypt"
        key_hex: SecretStr = Field(max_length=128)
        input: str = Field(max_length=24000)
        encoding: str = "base64"
        nonce_hex: str = Field(default="", max_length=64)
        aad: str = Field(default="", max_length=2000)
        authorisation: str = Field(min_length=5, max_length=1000)

    @core.app.get("/api/crypto")
    def listing():
        return {
            "algorithms": ALGORITHMS,
            "records": [
                {**r, "data": json.loads(r["data"])}
                for r in core.rows(
                    "SELECT * FROM crypto_records ORDER BY created DESC LIMIT 100"
                )
            ],
            "version": cryptography.__version__,
            "key_policy": "Keys are held only for the request and are never persisted or logged. Python does not guarantee memory zeroisation. Plaintext results are returned but not stored in history.",
        }

    @core.app.post("/api/crypto/run")
    def run(value: Experiment):
        if value.encoding not in ("utf8", "base64", "hex"):
            raise HTTPException(422, "Choose utf8, base64 or hex input")
        if value.operation == "decrypt" and value.encoding == "utf8":
            raise HTTPException(422, "Decrypt input must be ciphertext hex or Base64")
        rid = core.uid("CRYPTO")
        record = {
            "algorithm": value.algorithm,
            "operation": value.operation,
            "authorisation": value.authorisation,
            "nonce_hex": value.nonce_hex,
            "aad": value.aad,
            "key": "NOT STORED",
            "plaintext": "NOT STORED",
            "library": "pyca/cryptography",
            "library_version": cryptography.__version__,
            "validation": "EXPERIMENT / DOES NOT AUTHENTICATE SOURCE CLAIMS",
        }
        try:
            key = bytes.fromhex(value.key_hex.get_secret_value())
            data = (
                bytes.fromhex(value.input)
                if value.encoding == "hex"
                else base64.b64decode(value.input, validate=True)
                if value.encoding == "base64"
                else value.input.encode()
            )
            if len(data) > 16384:
                raise ValueError("Bounded laboratory input limit: 16,384 bytes")
            result, nonce = operate(
                value.algorithm,
                value.operation,
                key,
                data,
                bytes.fromhex(value.nonce_hex) if value.nonce_hex else None,
                value.aad.encode(),
            )
            record.update(
                {
                    "input_sha256": hashlib.sha256(data).hexdigest(),
                    "input_bytes": len(data),
                    "output_sha256": hashlib.sha256(result).hexdigest(),
                    "output_bytes": len(result),
                    "nonce_hex": nonce.hex() if nonce else None,
                    "status": "COMPLETE",
                    "authentication": "TAG VERIFIED"
                    if value.operation == "decrypt"
                    else "AUTHENTICATED CIPHERTEXT CREATED",
                }
            )
        except Exception:
            # Do not include secret-bearing validation exceptions in persistent records.
            record.update(
                {
                    "status": "FAILED",
                    "reason": "Authentication/key/nonce/input validation failed; no plaintext accepted.",
                }
            )
            core.execute(
                "INSERT INTO crypto_records VALUES(?,?,?)",
                (rid, core.now(), json.dumps(record)),
            )
            core.log(
                "crypto_experiment_failed", {"id": rid, "algorithm": value.algorithm}
            )
            raise HTTPException(422, {"experiment_id": rid, "reason": record["reason"]})
        core.execute(
            "INSERT INTO crypto_records VALUES(?,?,?)",
            (rid, core.now(), json.dumps(record)),
        )
        core.log(
            "crypto_experiment_complete", {"id": rid, "algorithm": value.algorithm}
        )
        return {
            "id": rid,
            **record,
            "output_base64": base64.b64encode(result).decode(),
            "output_hex": result.hex(),
            "output_text": result.decode("utf-8", "replace")
            if value.operation == "decrypt"
            else None,
        }

    return {"operate": operate}
