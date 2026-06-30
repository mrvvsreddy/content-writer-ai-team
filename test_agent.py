import asyncio
from app.agent.graph import run_agent

async def main():
    print(await run_agent("hello, who are you?"))
    print(await run_agent("how many articles pending?"))
    print(await run_agent("what did we just talk about?"))

asyncio.run(main())
