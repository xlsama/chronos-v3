import { SQL } from "bun";
import type { Executor } from "../types";

export const sqlExecutor: Executor = async (conn, operation, params) => {
  const sql = new SQL({
    hostname: (conn.host as string) || "localhost",
    port: (conn.port as number) || 5432,
    username: (conn.username as string) || "root",
    password: (conn.password as string) || "",
    database: (conn.database as string) || "",
  });

  try {
    const handlers: Record<string, () => Promise<unknown>> = {
      executeSql: async () => {
        const query = params.query as string;
        if (!query) throw new Error("参数 query 不能为空");
        const rows = await sql.unsafe(query);
        return rows;
      },

      listDatabases: async () => {
        const rows = await sql.unsafe(
          "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname",
        );
        return rows;
      },

      listTables: async () => {
        const schema = (params.schema as string) || "public";
        const rows = await sql.unsafe(
          `SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = '${schema}' ORDER BY table_name`,
        );
        return rows;
      },

      describeTable: async () => {
        const table = params.table as string;
        if (!table) throw new Error("参数 table 不能为空");
        const rows = await sql.unsafe(
          `SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name = '${table}' ORDER BY ordinal_position`,
        );
        return rows;
      },

      tableRowCount: async () => {
        const table = params.table as string;
        if (!table) throw new Error("参数 table 不能为空");
        const rows = await sql.unsafe(`SELECT COUNT(*) as count FROM "${table}"`);
        return rows;
      },
    };

    const handler = handlers[operation];
    if (!handler) {
      throw new Error(
        `PostgreSQL: unsupported operation "${operation}". Available: ${Object.keys(handlers).join(", ")}`,
      );
    }

    return await handler();
  } finally {
    await sql.close();
  }
};
