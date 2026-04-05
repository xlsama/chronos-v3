import type { CommandType } from "../types";

// ─── BLOCKED: 灾难性命令，直接拒绝 ─────────────────

const BLOCKED_PATTERNS: RegExp[] = [
  /rm\s+(-\w+\s+)*\/\s*$/,                  // rm /
  /rm\s+(-\w+\s+)*\/\*\s*$/,                // rm /*
  /rm\s+-\w*r\w*f\w*\s+\/($|\s)/,           // rm -rf /
  /rm\s+-\w*f\w*r\w*\s+\/($|\s)/,           // rm -fr /
  /:\s*\(\)\s*\{[^}]*:\s*\|\s*:\s*&/,       // fork bomb :(){ :|:& };:
  />\s*\/dev\/[hsn]/,                        // write to block devices (sd*, hd*, nvme*)
  /\bmkfs\b/,                                // format filesystem
  /\bdd\b.*\bof=\/dev\//,                    // dd to block device
  /\bchmod\s+(-\w+\s+)*777\s+\/($|\s)/,     // chmod 777 /
];

// ─── DANGEROUS: 破坏性命令，需要 HIGH 级审批 ────────

const DANGEROUS_PATTERNS: RegExp[] = [
  /\brm\s+-\w*r\w*f/,                       // rm -rf (any path)
  /\brm\s+-\w*f\w*r/,                       // rm -fr (any path)
  /\bkill\s+-9\b/,                           // kill -9
  /\bkillall\b/,                             // killall
  /\bpkill\b/,                               // pkill
  /\bsystemctl\s+(stop|disable|mask)\b/,     // systemctl stop/disable/mask
  /\bservice\s+\S+\s+stop\b/,               // service X stop
  /\bDROP\s+(TABLE|DATABASE|INDEX|SCHEMA)\b/i, // SQL DDL in shell (e.g. mysql -e)
  /\bTRUNCATE\b/i,                           // TRUNCATE in shell
  /\bDELETE\s+FROM\b/i,                      // DELETE FROM in shell
  /\biptables\b/,                            // firewall rules
  /\breboot\b/,                              // reboot
  /\bshutdown\b/,                            // shutdown
  /\binit\s+[06]\b/,                         // init 0/6
  /\bhalt\b/,                                // halt
  /\bdocker\s+(rm|rmi)\b/,                   // docker rm/rmi
  /\bdocker\s+system\s+prune\b/,             // docker system prune
  /\bkubectl\s+delete\b/,                    // kubectl delete
];

// ─── WRITE: 有副作用的命令，需要 MEDIUM 级审批 ──────

const WRITE_PATTERNS: RegExp[] = [
  /\bsed\s+-i\b/,                            // sed in-place
  /\bcurl\b.*(-X\s*(POST|PUT|PATCH|DELETE)|--data\b|-d\s)/i, // curl with body
  /\bwget\b(?!.*--spider)/,                  // wget (download, not spider)
  />\s/,                                      // output redirection
  />>/,                                       // append redirection
  /\|\s*tee\b/,                              // pipe to tee
  /\bmv\b/,                                  // move
  /\bcp\b/,                                  // copy
  /\bmkdir\b/,                               // mkdir
  /\btouch\b/,                               // touch
  /\bchmod\b/,                               // chmod (non-root, non-777-/)
  /\bchown\b/,                               // chown
  /\bln\b/,                                  // symlink
  /\bdocker\s+(start|stop|restart|pause|unpause|pull|build|exec|run)\b/, // docker write ops
  /\bdocker\s+compose\s+(up|down|restart|build)\b/, // docker compose write ops
  /\bkubectl\s+(apply|create|patch|edit|scale|rollout|expose|set|label|annotate|taint|cordon|uncordon|drain)\b/,
  /\bnpm\s+(install|uninstall|update|publish)\b/,
  /\bpip\s+install\b/,
  /\bapt(-get)?\s+(install|remove|update|upgrade)\b/,
  /\byum\s+(install|remove|update)\b/,
  /\bbrew\s+(install|uninstall|update|upgrade)\b/,
  /\bsystemctl\s+(start|restart|enable|reload)\b/, // systemctl write ops (not stop)
];

// ─── READ: 安全只读命令白名单 ───────────────────────

const READ_PATTERNS: RegExp[] = [
  // 文件系统检查
  /^ls\b/,
  /^dir\b/,
  /^cat\b/,
  /^head\b/,
  /^tail\b/,
  /^less\b/,
  /^more\b/,
  /^wc\b/,
  /^find\b/,
  /^file\b/,
  /^stat\b/,
  /^du\b/,
  /^df\b/,
  /^tree\b/,
  /^readlink\b/,

  // 文本处理（只读管道）
  /^grep\b/,
  /^egrep\b/,
  /^fgrep\b/,
  /^awk\b/,
  /^sed\b/,     // 不带 -i 的 sed（带 -i 已在 WRITE 中匹配）
  /^sort\b/,
  /^uniq\b/,
  /^cut\b/,
  /^diff\b/,
  /^jq\b/,
  /^yq\b/,

  // 进程/系统信息
  /^ps\b/,
  /^top\s+-b/,
  /^free\b/,
  /^uptime\b/,
  /^uname\b/,
  /^hostname\b/,
  /^whoami\b/,
  /^id\b/,
  /^w\b/,
  /^who\b/,
  /^lsof\b/,

  // 网络诊断
  /^ss\b/,
  /^netstat\b/,
  /^ifconfig\b/,
  /^ip\s+(addr|link|route|neigh|rule)\b/,
  /^nslookup\b/,
  /^dig\b/,
  /^ping\b/,
  /^traceroute\b/,
  /^tracepath\b/,
  /^mtr\b/,
  /^curl\s+(-s\s+)?-I\b/,      // curl -I (HEAD request)
  /^curl\s+.*--head\b/,         // curl --head
  /^wget\s+--spider\b/,         // wget spider mode

  // Docker 只读
  /^docker\s+(ps|images|inspect|logs|top|stats|info|version)\b/,
  /^docker\s+network\s+(ls|inspect)\b/,
  /^docker\s+volume\s+(ls|inspect)\b/,
  /^docker\s+compose\s+(ps|logs|config)\b/,

  // Kubernetes 只读
  /^kubectl\s+(get|describe|logs|top|explain|api-resources|api-versions|cluster-info|version)\b/,

  // systemd 只读
  /^systemctl\s+status\b/,
  /^journalctl\b/,

  // 时间
  /^date\b/,
  /^cal\b/,
  /^timedatectl\s+status\b/,

  // 环境变量
  /^env\b/,
  /^printenv\b/,
  /^echo\b/,
  /^printf\b/,
  /^pwd\b/,
  /^which\b/,
  /^type\b/,
];

// ─── 主分类函数 ───────────────────────────────────────

export function classifyShellCommand(command: string): CommandType {
  const trimmed = command.trim();
  if (!trimmed) return "read";

  // 1. BLOCKED — 全文扫描
  for (const re of BLOCKED_PATTERNS) {
    if (re.test(trimmed)) return "blocked";
  }

  // 2. DANGEROUS — 全文扫描
  for (const re of DANGEROUS_PATTERNS) {
    if (re.test(trimmed)) return "dangerous";
  }

  // 3. WRITE — 全文扫描（在 READ 之前，捕获管道中的写操作）
  for (const re of WRITE_PATTERNS) {
    if (re.test(trimmed)) return "write";
  }

  // 4. READ — 只检查管道第一段
  const firstCommand = trimmed.split(/\|/)[0].trim();
  for (const re of READ_PATTERNS) {
    if (re.test(firstCommand)) return "read";
  }

  // 5. 默认: fail-closed
  return "write";
}
