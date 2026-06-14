#!/usr/bin/env node
import { webcrypto } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const password = process.env.SITE_PASSWORD;
if (!password || password.length < 8) {
  throw new Error("SITE_PASSWORD must be set to at least 8 characters.");
}

const root = resolve(new URL("..", import.meta.url).pathname);
const inputPath = resolve(root, "build/cloud/plain-data.json");
const outputPath = resolve(root, "docs/encrypted-data.json");
const encoder = new TextEncoder();
const plain = await readFile(inputPath);
const salt = webcrypto.getRandomValues(new Uint8Array(16));
const iv = webcrypto.getRandomValues(new Uint8Array(12));
const baseKey = await webcrypto.subtle.importKey(
  "raw",
  encoder.encode(password),
  "PBKDF2",
  false,
  ["deriveKey"],
);
const iterations = 250000;
const key = await webcrypto.subtle.deriveKey(
  { name: "PBKDF2", hash: "SHA-256", salt, iterations },
  baseKey,
  { name: "AES-GCM", length: 256 },
  false,
  ["encrypt"],
);
const encrypted = new Uint8Array(await webcrypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plain));

function base64(bytes) {
  return Buffer.from(bytes).toString("base64");
}

await mkdir(dirname(outputPath), { recursive: true });
await writeFile(
  outputPath,
  JSON.stringify(
    {
      version: 1,
      algorithm: "AES-GCM",
      kdf: "PBKDF2-SHA-256",
      iterations,
      salt: base64(salt),
      iv: base64(iv),
      ciphertext: base64(encrypted),
    },
    null,
    2,
  ) + "\n",
  "utf8",
);
console.log(outputPath);
