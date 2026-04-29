# d.json Export for Axon Ivy

This fork of [drawDB](https://github.com/drawdb-io/drawdb) adds an export feature that converts your database diagram directly into **Axon Ivy 12 d.json dataclass files**, ready to use in your Axon Ivy project.

---

## Export d.json from the Diagram Editor

To try the export with a ready-made example:
- Create a new **Generic** project in the drawdb frontend
- Import the `example/company_example.json` file via **File → Import diagram**

The imported diagram shows a small company schema with four tables and relationships of every supported association type:

<img width="1075" height="471" alt="image" src="https://github.com/user-attachments/assets/4d741449-e860-402d-b4fb-496bcfcf3a44" />

In the diagram editor, open **File → Export SQL → d.json (Axon Ivy)**.

A dialog will appear with the following options:

| Option | Description |
|---|---|
| **Namespace** | Java package path for the generated classes, e.g. `drawdb.entities` |
| **Prefix** | Optional prefix added to class and table names, e.g. `History` → `HistoryCompany` |
| **Use Default ID** | Emits the `GENERATED` modifier on the id field instead of `@SequenceGenerator` annotations |
| **Single mode** | Use when your diagram contains exactly one table; enables the Table Name Override option |
| **Table Name Override** | *(Single mode only)* Overrides the entity `tableName` in the generated d.json |

Click **Export** to download a `.zip` file containing:
- One `.d.json` file per table
- `input.sql` — the PostgreSQL DDL that was used as input
- `warnings.log` — any SQL types that could not be mapped and were fallen back to `String`

The d.json files can be copied into an Axon Ivy 12 project:
<img width="1888" height="796" alt="image" src="https://github.com/user-attachments/assets/24c571fc-54cc-41ee-a04d-d6b0cf4d1691" />


> **Note:** The export requires the backend service to be running (see Setup below).


---

## Association Types

A key feature of the d.json export is that foreign key columns are not exported as plain integer IDs — they are resolved into proper JPA associations with typed object references. All three standard JPA association types are supported.

### MANY_TO_ONE / ONE_TO_MANY

A regular foreign key (no `UNIQUE` constraint) is treated as a many-to-one relationship. The exporter generates:
- A **`MANY_TO_ONE`** field on the owning side (the table holding the FK), replacing the raw FK column with a typed object reference
- A **`ONE_TO_MANY`** field (`java.util.Set<...>`) on the referenced side, with `mappedByFieldName` pointing back to the owning field

**Example** — `department.company_id` references `company.id`:

`Department.d.json`:
```json
{ "name": "company", "type": "com.example.entities.Company",
  "entity": { "association": "MANY_TO_ONE", ... } }
```

`Company.d.json`:
```json
{ "name": "departmenten", "type": "java.util.Set<com.example.entities.Department>",
  "entity": { "association": "ONE_TO_MANY", "mappedByFieldName": "company", ... } }
```

### ONE_TO_ONE

When a foreign key column is marked as **UNIQUE** in the diagram (or the relationship cardinality is set to `1:1`), it is treated as a one-to-one relationship. The exporter generates:
- A **`ONE_TO_ONE`** field on the owning side (the table holding the FK)
- A **`ONE_TO_ONE`** field on the referenced side with `mappedByFieldName`, using a singular type (not a `Set`)

**Example** — `boss.employee_id` references `employee.id` with a 1:1 cardinality:

`Boss.d.json`:
```json
{ "name": "employee", "type": "com.example.entities.Employee",
  "entity": { "association": "ONE_TO_ONE", ... } }
```

`Employee.d.json`:
```json
{ "name": "boss", "type": "com.example.entities.Boss",
  "entity": { "association": "ONE_TO_ONE", "mappedByFieldName": "employee", ... } }
```

> **Tip:** To get `ONE_TO_ONE` output, either mark the FK column as `UNIQUE` in the drawdb field editor, or set the relationship cardinality to `1:1` via the relationship properties panel.

---

## Setup

### Prerequisites
- [Docker](https://www.docker.com/) or [Rancher Desktop](https://rancherdesktop.io/)
- If running from WSL: always start from the WSL terminal, not from Docker Desktop GUI

### Start with Docker Compose

```bash
git clone https://github.com/YOUR_USERNAME/drawdb-djson-creator.git
cd drawdb-djson-creator
docker compose up --build
```

Then open [http://localhost:5173](http://localhost:5173) in your browser.

This starts two services:
- **drawdb** (frontend) on port `5173`
- **drawdb-backend** (Python API) on port `8000`

---

## sql_to_djson.py — CLI Tool

The backend uses `sql_to_djson.py`, a standalone Python script that converts PostgreSQL DDL files into Axon Ivy 12 d.json dataclass files. It can also be used independently from the command line.

### Installation

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn python-multipart
```

### Usage

**Multi mode** — generates one d.json file per `CREATE TABLE`:

```bash
python sql_to_djson.py input.sql --namespace com.example.entities --output ./out/
```

**With a class/table prefix:**

```bash
python sql_to_djson.py input.sql --namespace com.example.entities --prefix History --output ./out/
```

**With default ID** (uses `GENERATED` modifier instead of `@SequenceGenerator`):

```bash
python sql_to_djson.py input.sql --namespace com.example.entities --useDefaultId --output ./out/
```

**Single mode** — for SQL files with exactly one table, with optional overrides:

```bash
python sql_to_djson.py input.sql --namespace com.example.entities --single
python sql_to_djson.py input.sql --namespace com.example.entities --single --tableName my_table
python sql_to_djson.py input.sql --namespace com.example.entities --single --tableName my_table --prefix History
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `input` | ✅ | Path to the input SQL DDL file |
| `--namespace` | ✅ | Java namespace for generated classes, e.g. `com.example.entities` |
| `--output` | | Output directory (default: current directory) |
| `--prefix` | | Optional prefix for class and table names, e.g. `History` |
| `--useDefaultId` | | Emit `GENERATED` modifier on id instead of `@SequenceGenerator` annotations |
| `--single` | | Single mode: SQL must contain exactly one `CREATE TABLE` |
| `--tableName` | | *(Single mode only)* Override the entity `tableName`. Combined with `--prefix` if given. |

### Output

For each table, a file named `<ClassName>.d.json` is written to the output directory. If any SQL types could not be mapped to a known Java type, a `warnings.log` file is also written listing the affected tables and columns.

**SQL type mapping:**

| SQL Type | Java Type |
|---|---|
| `int`, `int4`, `integer`, `smallint` | `Integer` |
| `int8`, `bigint`, `bigserial` | `Long` |
| `varchar`, `text`, `char` | `String` |
| `boolean` | `Boolean` |
| `date`, `timestamp` | `java.util.Date` |
| `numeric`, `decimal` | `java.math.BigDecimal` |
| `float4`, `real` | `Float` |
| `float8`, `double precision` | `Double` |
| *(unknown)* | `String` *(with warning)* |
