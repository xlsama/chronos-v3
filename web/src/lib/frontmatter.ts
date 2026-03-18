import fm from "front-matter";

export function parseFrontmatter(content: string) {
  try {
    const { attributes, body } = fm<{ name?: string; description?: string }>(content);
    return {
      name: attributes.name ?? "",
      description: attributes.description ?? "",
      body,
    };
  } catch {
    return { name: "", description: "", body: content };
  }
}
