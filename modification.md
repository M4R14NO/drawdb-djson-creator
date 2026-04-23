# d.json Export for Axon Ivy

This fork of [drawDB](https://github.com/drawdb-io/drawdb) adds an export feature that converts your database diagram directly into **Axon Ivy 12 d.json dataclass files**, ready to use in your Axon Ivy project.

---

## Export d.json from the Diagram Editor

In the diagram editor, open **File → Export SQL → d.json (Axon Ivy)**.

A dialog will appear with the following options:

| Option | Description |
|---|---|
| **Namespace** | Java package path for the generated classes, e.g. `com.example.entities` |
| **Prefix** | Optional prefix added to class and table names, e.g. `History` → `HistoryKategorie` |
| **Use Default ID** | Emits the `GENERATED` modifier on the id field instead of `@SequenceGenerator` annotations |
| **Single mode** | Use when your diagram contains exactly one table; enables the Table Name Override option |
| **Table Name Override** | *(Single mode only)* Overrides the entity `tableName` in the generated d.json |

Click **Export** to download a `.zip` file containing:
- One `.d.json` file per table
- `input.sql` — the PostgreSQL DDL that was used as input
- `warnings.log` — any SQL types that could not be mapped and were fallen back to `String`

> **Note:** The export requires the backend service to be running (see Setup below).

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
