import { jsonToPostgreSQL } from "./exportSQL/generic";

export function exportDJson(tables, relationships, types, database, namespace) {
  const sql = jsonToPostgreSQL({ tables, references: relationships, types, database });

  const form = new FormData();
  form.append("sql", sql);
  form.append("namespace", namespace);

  fetch("http://localhost:8000/api/export-djson", {
    method: "POST",
    body: form,
  })
    .then((res) => res.blob())
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "djson.zip";
      a.click();
    });
}
