import mysql from "mysql2/promise";
import type { Executor } from "../types";

export const mysqlExecutor: Executor = async (conn, operation, params) => {
  const connection = await mysql.createConnection({
    host: (conn.host as string) || "localhost",
    port: (conn.port as number) || 3306,
    user: (conn.username as string) || "root",
    password: (conn.password as string) || "",
    database: (conn.database as string) || undefined,
  });

  try {
    const handlers: Record<string, () => Promise<unknown>> = {
      executeSql: async () => {
        const query = params.query as string;
        if (!query) throw new Error("参数 query 不能为空");
        const [rows] = await connection.query(query);
        return rows;
      },

      listDatabases: async () => {
        const [rows] = await connection.query("SHOW DATABASES");
        return rows;
      },

      listTables: async () => {
        const schema = (params.schema as string) || conn.database;
        if (schema) {
          const [rows] = await connection.query(
            `SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = ? ORDER BY table_name`,
            [schema],
          );
          return rows;
        }
        const [rows] = await connection.query("SHOW TABLES");
        return rows;
      },

      describeTable: async () => {
        const table = params.table as string;
        if (!table) throw new Error("参数 table 不能为空");
        const [rows] = await connection.query(
          `SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name = ? AND table_schema = DATABASE() ORDER BY ordinal_position`,
          [table],
        );
        return rows;
      },

      tableRowCount: async () => {
        const table = params.table as string;
        if (!table) throw new Error("参数 table 不能为空");
        const [rows] = await connection.query(`SELECT COUNT(*) as count FROM \`${table}\``);
        return rows;
      },
    };

    const handler = handlers[operation];
    if (!handler) {
      throw new Error(
        `MySQL: unsupported operation "${operation}". Available: ${Object.keys(handlers).join(", ")}`,
      );
    }

    return await handler();
  } finally {
    await connection.end();
  }
};
