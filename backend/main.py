from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import subprocess, tempfile, zipfile, os, logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/api/export-djson")
async def export_djson(
    sql: str = Form(...),
    namespace: str = Form(...),
    prefix: str = Form(""),
    useDefaultId: str = Form("false"),
    single: str = Form("false"),
    tableName: str = Form(""),
):
    with tempfile.TemporaryDirectory() as tmpdir:
        sql_file = os.path.join(tmpdir, "input.sql")
        out_dir  = os.path.join(tmpdir, "out")
        os.makedirs(out_dir)

        with open(sql_file, "w") as f:
            f.write(sql)

        cmd = ["python3", "sql_to_djson.py", sql_file, "--namespace", namespace, "--output", out_dir]
        if prefix:
            cmd += ["--prefix", prefix]
        if useDefaultId == "true":
            cmd += ["--useDefaultId"]
        if single == "true":
            cmd += ["--single"]
            if tableName:
                cmd += ["--tableName", tableName]

        # Also save the SQL into the output dir for reference
        sql_ref_path = os.path.join(out_dir, "input.sql")
        with open(sql_ref_path, "w") as f:
            f.write(sql)
        
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"sql_to_djson.py failed:\n{result.stderr}")

        out_files = os.listdir(out_dir)
        if not out_files:
            raise HTTPException(status_code=500, detail="No d.json files were generated")

        zip_path = os.path.join(tmpdir, "djson.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            for fname in out_files:
                zf.write(os.path.join(out_dir, fname), fname)

        with open(zip_path, "rb") as f:
            zip_bytes = f.read()

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=djson.zip"}
    )
