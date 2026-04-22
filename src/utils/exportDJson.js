import { jsonToPostgreSQL } from "./exportSQL/generic";

export function exportDJson(tables, relationships, types, database, options) {
  const { namespace, prefix, useDefaultId, single, tableName } = options;

  const sql = jsonToPostgreSQL({ tables, references: relationships, types, database });

  const form = new FormData();
  form.append("sql", sql);
  form.append("namespace", namespace);
  form.append("prefix", prefix || "");
  form.append("useDefaultId", useDefaultId ? "true" : "false");
  form.append("single", single ? "true" : "false");
  form.append("tableName", tableName || "");

  fetch("http://localhost:8000/api/export-djson", {
    method: "POST",
    body: form,
  })
    .then((res) => {
      if (!res.ok) return res.text().then(t => { throw new Error(t); });
      return res.blob();
    })
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "djson.zip";
      a.click();
    })
    .catch((err) => alert("Export failed: " + err.message));
}
