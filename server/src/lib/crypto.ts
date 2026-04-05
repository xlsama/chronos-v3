import { env } from "@/env";

const NONCE_LENGTH = 12;

function createCryptoService(base64Key: string) {
  const keyBytes = Buffer.from(base64Key, "base64");
  if (keyBytes.length !== 32) {
    throw new Error(`ENCRYPTION_KEY must be exactly 32 bytes, got ${keyBytes.length}`);
  }

  let cryptoKey: CryptoKey | null = null;

  async function getKey(): Promise<CryptoKey> {
    if (!cryptoKey) {
      cryptoKey = await crypto.subtle.importKey(
        "raw",
        keyBytes,
        "AES-GCM",
        false,
        ["encrypt", "decrypt"],
      );
    }
    return cryptoKey;
  }

  return {
    async encrypt(plaintext: string): Promise<string> {
      const key = await getKey();
      const nonce = crypto.getRandomValues(new Uint8Array(NONCE_LENGTH));
      const encoded = new TextEncoder().encode(plaintext);
      const ciphertext = new Uint8Array(
        await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, encoded),
      );
      // nonce(12) + ciphertext + authTag(16)
      const result = new Uint8Array(nonce.length + ciphertext.length);
      result.set(nonce);
      result.set(ciphertext, nonce.length);
      return Buffer.from(result).toString("base64");
    },

    async decrypt(token: string): Promise<string> {
      const key = await getKey();
      const raw = Buffer.from(token, "base64");
      const nonce = raw.subarray(0, NONCE_LENGTH);
      const ciphertext = raw.subarray(NONCE_LENGTH);
      const decrypted = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: nonce },
        key,
        ciphertext,
      );
      return new TextDecoder().decode(decrypted);
    },
  };
}

export const cryptoService = createCryptoService(env.ENCRYPTION_KEY);
