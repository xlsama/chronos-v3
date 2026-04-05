import { db } from "@/db/connection";
import { contentVersions } from "@/db/schema";
import { and, desc, eq } from "drizzle-orm";

export async function saveVersion(
  entityType: string,
  entityId: string,
  content: string,
  changeSource = "manual",
) {
  const [latest] = await db
    .select()
    .from(contentVersions)
    .where(
      and(
        eq(contentVersions.entityType, entityType),
        eq(contentVersions.entityId, entityId),
      ),
    )
    .orderBy(desc(contentVersions.versionNumber))
    .limit(1);

  // Deduplicate: skip if content hasn't changed
  if (latest && latest.content === content) {
    return latest;
  }

  const versionNumber = latest ? latest.versionNumber + 1 : 1;
  const [version] = await db
    .insert(contentVersions)
    .values({ entityType, entityId, content, versionNumber, changeSource })
    .returning();
  return version;
}

export async function listVersions(entityType: string, entityId: string) {
  return db
    .select()
    .from(contentVersions)
    .where(
      and(
        eq(contentVersions.entityType, entityType),
        eq(contentVersions.entityId, entityId),
      ),
    )
    .orderBy(desc(contentVersions.versionNumber));
}

export async function deleteVersions(entityType: string, entityId: string) {
  await db
    .delete(contentVersions)
    .where(
      and(
        eq(contentVersions.entityType, entityType),
        eq(contentVersions.entityId, entityId),
      ),
    );
}

export async function getVersion(versionId: string) {
  const [version] = await db
    .select()
    .from(contentVersions)
    .where(eq(contentVersions.id, versionId));
  return version;
}
