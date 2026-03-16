import { execSync } from "child_process";
import { resolve } from "path";

export class TestInfra {
  private composeFile: string;
  private projectName: string;

  constructor(caseName: string) {
    this.composeFile = resolve(import.meta.dirname, `../${caseName}/docker-compose.yml`);
    this.projectName = `chronos-e2e-${caseName}`;
  }

  start(): void {
    console.log(`[infra] Starting ${this.projectName}...`);
    execSync(
      `docker compose -f ${this.composeFile} -p ${this.projectName} up -d --wait`,
      { stdio: "inherit", timeout: 180_000 },
    );
    console.log(`[infra] ${this.projectName} is up`);
  }

  stop(): void {
    console.log(`[infra] Stopping ${this.projectName}...`);
    try {
      execSync(
        `docker compose -f ${this.composeFile} -p ${this.projectName} down -v --remove-orphans`,
        { stdio: "inherit", timeout: 60_000 },
      );
    } catch (e) {
      console.warn(`[infra] Warning during stop: ${e}`);
    }
  }
}
