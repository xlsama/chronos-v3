import { describe, it, expect } from "vitest";
import { classifyShellCommand } from "@/ops-agent/safety/shell-classifier";

describe("ShellSafety Classifier", () => {
  // ── BLOCKED: 灾难性命令 ─────────────────────────────

  describe("BLOCKED — catastrophic commands", () => {
    it.each([
      ["rm -rf /", "blocked"],
      ["rm -rf /*", "blocked"],
      ["rm -fr /", "blocked"],
      ["rm /", "blocked"],
      [":(){ :|:& };:", "blocked"],
      ["> /dev/sda", "blocked"],
      ["dd if=/dev/zero of=/dev/sda bs=1M", "blocked"],
      ["mkfs.ext4 /dev/sda1", "blocked"],
      ["chmod 777 /", "blocked"],
    ] as const)("%s → %s", (cmd, expected) => {
      expect(classifyShellCommand(cmd)).toBe(expected);
    });
  });

  // ── DANGEROUS: 破坏性命令 ───────────────────────────

  describe("DANGEROUS — destructive commands", () => {
    it.each([
      ["rm -rf /tmp/data", "dangerous"],
      ["rm -fr ./build", "dangerous"],
      ["kill -9 12345", "dangerous"],
      ["killall nginx", "dangerous"],
      ["pkill -f node", "dangerous"],
      ["systemctl stop nginx", "dangerous"],
      ["systemctl disable sshd", "dangerous"],
      ["service nginx stop", "dangerous"],
      ["docker rm abc123", "dangerous"],
      ["docker rmi myimage:latest", "dangerous"],
      ["docker system prune", "dangerous"],
      ["kubectl delete pod mypod", "dangerous"],
      ["kubectl delete deployment nginx", "dangerous"],
      ["reboot", "dangerous"],
      ["shutdown -h now", "dangerous"],
      ["halt", "dangerous"],
      ["init 0", "dangerous"],
      ["iptables -F", "dangerous"],
      ["mysql -e 'DROP TABLE users'", "dangerous"],
      ["echo test | mysql -e 'TRUNCATE users'", "dangerous"],
    ] as const)("%s → %s", (cmd, expected) => {
      expect(classifyShellCommand(cmd)).toBe(expected);
    });
  });

  // ── READ: 安全只读命令 ──────────────────────────────

  describe("READ — safe read-only commands", () => {
    it.each([
      // 文件系统
      ["ls -la", "read"],
      ["ls -la /var/log", "read"],
      ["cat /var/log/syslog", "read"],
      ["head -n 100 /var/log/syslog", "read"],
      ["tail -f /var/log/syslog", "read"],
      ["wc -l /var/log/syslog", "read"],
      ["find /tmp -name '*.log'", "read"],
      ["file /usr/bin/ls", "read"],
      ["stat /etc/hosts", "read"],
      ["du -sh /tmp", "read"],
      ["df -h", "read"],

      // 文本处理
      ["grep -r 'error' /var/log/", "read"],
      ["awk '{print $1}' access.log", "read"],
      ["sed 's/old/new/g' config.txt", "read"], // sed 不带 -i
      ["sort file.txt", "read"],
      ["jq '.name' package.json", "read"],
      ["cut -d: -f1 /etc/passwd", "read"],

      // 进程/系统
      ["ps aux", "read"],
      ["free -m", "read"],
      ["uptime", "read"],
      ["uname -a", "read"],
      ["hostname", "read"],
      ["whoami", "read"],
      ["id", "read"],
      ["lsof -i :80", "read"],

      // 网络
      ["ss -tlnp", "read"],
      ["netstat -tlnp", "read"],
      ["ping -c 3 google.com", "read"],
      ["dig google.com", "read"],
      ["nslookup example.com", "read"],
      ["curl -I https://example.com", "read"],
      ["curl --head https://example.com", "read"],
      ["traceroute google.com", "read"],

      // Docker 只读
      ["docker ps", "read"],
      ["docker ps -a", "read"],
      ["docker logs abc123", "read"],
      ["docker inspect abc123", "read"],
      ["docker stats", "read"],
      ["docker images", "read"],
      ["docker info", "read"],
      ["docker network ls", "read"],
      ["docker volume ls", "read"],
      ["docker compose ps", "read"],
      ["docker compose logs -f", "read"],

      // Kubernetes 只读
      ["kubectl get pods", "read"],
      ["kubectl get pods -n kube-system", "read"],
      ["kubectl describe pod mypod", "read"],
      ["kubectl logs mypod -f", "read"],
      ["kubectl top pods", "read"],
      ["kubectl cluster-info", "read"],

      // systemd 只读
      ["systemctl status nginx", "read"],
      ["journalctl -u nginx --no-pager -n 100", "read"],

      // 环境/时间
      ["env", "read"],
      ["printenv HOME", "read"],
      ["echo hello", "read"],
      ["date", "read"],
      ["pwd", "read"],
      ["which python", "read"],
    ] as const)("%s → %s", (cmd, expected) => {
      expect(classifyShellCommand(cmd)).toBe(expected);
    });
  });

  // ── WRITE: 有副作用的命令 ───────────────────────────

  describe("WRITE — side-effect commands", () => {
    it.each([
      ["sed -i 's/old/new/g' config.txt", "write"],
      ["curl -X POST http://api.example.com/data -d '{}'", "write"],
      ["curl --data '{\"key\":\"val\"}' http://api.example.com", "write"],
      ["wget https://example.com/file.tar.gz", "write"],
      ["mv /tmp/a /tmp/b", "write"],
      ["cp /tmp/a /tmp/b", "write"],
      ["mkdir -p /tmp/newdir", "write"],
      ["touch /tmp/newfile", "write"],
      ["chmod 644 /tmp/file", "write"],
      ["chown user:group /tmp/file", "write"],
      ["ln -s /tmp/a /tmp/b", "write"],
      ["echo 'data' > /tmp/file", "write"],
      ["cat file >> /tmp/output", "write"],
      ["docker start abc123", "write"],
      ["docker stop abc123", "write"],
      ["docker restart abc123", "write"],
      ["docker run nginx", "write"],
      ["docker exec -it abc123 bash", "write"],
      ["docker pull nginx:latest", "write"],
      ["docker compose up -d", "write"],
      ["docker compose down", "write"],
      ["kubectl apply -f deployment.yaml", "write"],
      ["kubectl scale deployment nginx --replicas=3", "write"],
      ["kubectl rollout restart deployment nginx", "write"],
      ["kubectl drain node1", "write"],
      ["npm install express", "write"],
      ["pip install requests", "write"],
      ["systemctl restart nginx", "write"],
      ["systemctl enable nginx", "write"],
    ] as const)("%s → %s", (cmd, expected) => {
      expect(classifyShellCommand(cmd)).toBe(expected);
    });
  });

  // ── 管道和重定向组合 ────────────────────────────────

  describe("pipes and redirects", () => {
    it("ps aux | grep nginx → read（管道首段是 read）", () => {
      expect(classifyShellCommand("ps aux | grep nginx")).toBe("read");
    });

    it("grep error log.txt | wc -l → read", () => {
      expect(classifyShellCommand("grep error log.txt | wc -l")).toBe("read");
    });

    it("cat file | tee /tmp/copy → write（tee 写文件）", () => {
      expect(classifyShellCommand("cat file | tee /tmp/copy")).toBe("write");
    });

    it("ls > /tmp/list.txt → write（重定向）", () => {
      expect(classifyShellCommand("ls > /tmp/list.txt")).toBe("write");
    });

    it("ps aux | xargs kill -9 → dangerous（管道中有 kill -9）", () => {
      expect(classifyShellCommand("ps aux | xargs kill -9")).toBe("dangerous");
    });

    it("cat /etc/hosts >> /tmp/output → write（追加重定向）", () => {
      expect(classifyShellCommand("cat /etc/hosts >> /tmp/output")).toBe("write");
    });
  });

  // ── 边界情况 ────────────────────────────────────────

  describe("edge cases", () => {
    it("空字符串 → read", () => {
      expect(classifyShellCommand("")).toBe("read");
    });

    it("纯空格 → read", () => {
      expect(classifyShellCommand("   ")).toBe("read");
    });

    it("未知命令 → write (fail-closed)", () => {
      expect(classifyShellCommand("some-unknown-command --flag")).toBe("write");
    });

    it("wget --spider → read（不下载）", () => {
      expect(classifyShellCommand("wget --spider https://example.com")).toBe("read");
    });

    it("curl (无参数，GET 请求) → write (fail-closed，可能下载)", () => {
      expect(classifyShellCommand("curl https://example.com")).toBe("write");
    });
  });
});
