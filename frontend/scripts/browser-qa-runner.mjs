import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDir, "..");
const viteBin = resolve(frontendRoot, "node_modules", "vite", "bin", "vite.js");

function getFreePort() {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolvePort(address.port));
    });
  });
}

async function waitForServer(url, timeoutMs = 30000) {
  const startedAt = Date.now();
  let lastError = null;
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Vite preview did not become ready at ${url}: ${lastError?.message || "timeout"}`);
}

function runCommand(command, args, options = {}) {
  return new Promise((resolveRun, reject) => {
    const child = spawn(command, args, {
      cwd: frontendRoot,
      stdio: "inherit",
      shell: false,
      ...options,
    });
    child.on("error", reject);
    child.on("exit", (code, signal) => {
      if (code === 0) resolveRun();
      else reject(new Error(`${command} ${args.join(" ")} exited with ${code ?? signal}`));
    });
  });
}

async function stopProcess(child) {
  if (!child || child.exitCode !== null) return;
  await new Promise((resolveStop) => {
    child.once("exit", resolveStop);
    child.kill("SIGTERM");
    setTimeout(() => {
      if (child.exitCode === null) child.kill("SIGKILL");
    }, 3000).unref();
  });
}

let preview = null;

try {
  const baseUrl = process.env.QA_BASE_URL;
  if (baseUrl) {
    await runCommand(process.execPath, ["scripts/browser-qa-sales.mjs"], {
      env: { ...process.env, QA_BASE_URL: baseUrl },
    });
  } else {
    const port = await getFreePort();
    const localBaseUrl = `http://127.0.0.1:${port}`;
    preview = spawn(
      process.execPath,
      [viteBin, "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
      {
        cwd: frontendRoot,
        stdio: ["ignore", "pipe", "pipe"],
        shell: false,
      },
    );
    preview.stdout.on("data", (chunk) => process.stdout.write(chunk));
    preview.stderr.on("data", (chunk) => process.stderr.write(chunk));
    await waitForServer(localBaseUrl);
    await runCommand(process.execPath, ["scripts/browser-qa-sales.mjs"], {
      env: { ...process.env, QA_BASE_URL: localBaseUrl },
    });
  }
} finally {
  await stopProcess(preview);
}
