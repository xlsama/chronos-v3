import { MongoClient } from "mongodb";
import type { Executor } from "../types";

function buildMongoUri(conn: Record<string, unknown>): string {
  if (conn.uri) return conn.uri as string;
  const host = (conn.host as string) || "localhost";
  const port = (conn.port as number) || 27017;
  const username = conn.username as string | undefined;
  const password = conn.password as string | undefined;
  if (username && password) {
    return `mongodb://${username}:${password}@${host}:${port}`;
  }
  return `mongodb://${host}:${port}`;
}

export const mongoExecutor: Executor = async (conn, operation, params) => {
  const uri = buildMongoUri(conn);
  const client = new MongoClient(uri);

  try {
    await client.connect();
    const dbName = (params.database as string) || (conn.database as string) || "test";
    const mdb = client.db(dbName);

    const handlers: Record<string, () => Promise<unknown>> = {
      // ── Read ──
      listDatabases: async () => {
        const result = await client.db("admin").command({ listDatabases: 1 });
        return result.databases;
      },

      listCollections: async () => {
        const collections = await mdb.listCollections().toArray();
        return collections.map((c) => ({ name: c.name, type: c.type }));
      },

      findDocuments: async () => {
        const collection = params.collection as string;
        if (!collection) throw new Error("参数 collection 不能为空");
        const filter = (params.filter as Record<string, unknown>) || {};
        const limit = (params.limit as number) || 100;
        const sort = params.sort as Record<string, 1 | -1> | undefined;
        let cursor = mdb.collection(collection).find(filter).limit(limit);
        if (sort) cursor = cursor.sort(sort);
        return cursor.toArray();
      },

      countDocuments: async () => {
        const collection = params.collection as string;
        if (!collection) throw new Error("参数 collection 不能为空");
        const filter = (params.filter as Record<string, unknown>) || {};
        return mdb.collection(collection).countDocuments(filter);
      },

      aggregate: async () => {
        const collection = params.collection as string;
        if (!collection) throw new Error("参数 collection 不能为空");
        const pipeline = (params.pipeline as Record<string, unknown>[]) || [];
        return mdb.collection(collection).aggregate(pipeline).toArray();
      },

      // ── Write ──
      insertOne: async () => {
        const collection = params.collection as string;
        if (!collection) throw new Error("参数 collection 不能为空");
        const document = params.document as Record<string, unknown>;
        if (!document) throw new Error("参数 document 不能为空");
        return mdb.collection(collection).insertOne(document);
      },

      updateMany: async () => {
        const collection = params.collection as string;
        if (!collection) throw new Error("参数 collection 不能为空");
        const filter = (params.filter as Record<string, unknown>) || {};
        const update = params.update as Record<string, unknown>;
        if (!update) throw new Error("参数 update 不能为空");
        return mdb.collection(collection).updateMany(filter, update);
      },

      // ── Dangerous ──
      deleteMany: async () => {
        const collection = params.collection as string;
        if (!collection) throw new Error("参数 collection 不能为空");
        const filter = (params.filter as Record<string, unknown>) || {};
        return mdb.collection(collection).deleteMany(filter);
      },
    };

    const handler = handlers[operation];
    if (!handler) {
      throw new Error(
        `MongoDB: unsupported operation "${operation}". Available: ${Object.keys(handlers).join(", ")}`,
      );
    }

    return await handler();
  } finally {
    await client.close();
  }
};
