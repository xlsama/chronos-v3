import { Client } from "ssh2";

export interface SSHConfig {
  host: string;
  port: number;
  username: string;
  password: string;
}

const DEFAULT_SSH_CONFIG: SSHConfig = {
  host: "localhost",
  port: 12222,
  username: "root",
  password: "testpassword",
};

export class FaultInjector {
  private config: SSHConfig;

  constructor(config?: Partial<SSHConfig>) {
    this.config = { ...DEFAULT_SSH_CONFIG, ...config };
  }

  async exec(cmd: string): Promise<{ stdout: string; stderr: string; code: number }> {
    return new Promise((resolve, reject) => {
      const conn = new Client();
      conn
        .on("ready", () => {
          conn.exec(cmd, (err, stream) => {
            if (err) {
              conn.end();
              return reject(err);
            }
            let stdout = "";
            let stderr = "";
            stream.on("data", (d: Buffer) => (stdout += d.toString()));
            stream.stderr.on("data", (d: Buffer) => (stderr += d.toString()));
            stream.on("close", (code: number) => {
              conn.end();
              resolve({ stdout, stderr, code: code ?? 0 });
            });
          });
        })
        .on("error", reject)
        .connect(this.config);
    });
  }

  async injectDiskFull(): Promise<void> {
    await this.exec("fallocate -l 450M /tmp/testfill");
  }

  async killProcess(name: string): Promise<void> {
    await this.exec(`pkill -f "${name}"`);
  }

  async isProcessRunning(name: string): Promise<boolean> {
    const result = await this.exec(`pgrep -f "${name}"`);
    return result.code === 0;
  }
}
