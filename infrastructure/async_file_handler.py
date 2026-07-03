import aiofiles
class AsyncFileHandler:
    def __init__(self, file_name):
        self.file_name = file_name
    
    async def create_file(self): 
        self.file = await aiofiles.open(self.file_name, mode='w')
    
    async def write_line(self, data):
        text = str(data)
        await self.file.write(text+"\n")
        await self.file.flush()
        
    async def close_file(self):
        if hasattr(self, 'file'):
            await self.file.close()