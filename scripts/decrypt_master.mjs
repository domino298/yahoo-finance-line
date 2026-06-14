#!/usr/bin/env node
import { webcrypto } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const password = process.env.SITE_PASSWORD;
if (!password || password.length < 8) {
  throw new Error("SITE_PASSWORD must be set to at least 8 characters.");
}

const root = resolve(new URL("..", import.meta.url).pathname);
const inputPath = resolve(root, "data/master-xlsx.enc.json");
const outputPath = resolve(root, "outputs/yahoo_finance_portfolio_backup.xlsx");
const encrypted = JSON.parse(await readFile(inputPath, "utf8"));
const encoder = new TextEncoder();

function bytesFromBase64(text) {
  return Uint8Array.from(Buffer.from(text, "base64"));
}

const baseKey = await webcrypto.subtle.importKey(
  "raw",
  encoder.encode(password),
  "PBKDF2",
  false,
  ["deriveKey"],
);
const key = await webcrypto.subtle.deriveKey(
  {
    name: "PBKDF2",
    hash: "SHA-256",
    salt: bytesFromBase64(encrypted.salt),
    iterations: encrypted.iterations,
  },
  baseKey,
  { name: "AES-GCM", length: 256 },
  false,
  ["decrypt"],
);
const plain = new Uint8Array(
  await webcrypto.subtle.decrypt(
    { name: "AES-GCM", iv: bytesFromBase64(encrypted.iv) },
    key,
    bytesFromBase64(encrypted.ciphertext),
  ),
);
await mkdir(dirname(outputPath), { recursive: true });
await writeFile(outputPath, plain);
console.log(outputPath);
