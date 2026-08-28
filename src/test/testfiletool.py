import asyncio
from src.tools.read_file import ReadFileTool


async def main():
    tool = ReadFileTool(base_dir="./sandbox")

    print(await tool.execute({"path": "notes.txt"}))              # works, if file exists
    print(await tool.execute({"path": "../../etc/passwd"}))       # Error: escapes sandbox
    print(await tool.execute({"path": "/etc/passwd"}))            # Error: absolute paths not allowed
    print(await tool.execute({"path": "subdir/../../secrets"}))   # Error: escapes sandbox


asyncio.run(main())