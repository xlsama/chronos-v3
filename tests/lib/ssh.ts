import { Client } from "ssh2";

export class FaultInjector {
  private config = {
    host: "localhost",
    port: 12222,
    username: "root",
    password: "testpassword",
  };

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
}
