from backend.memory.buffer import add_message,get_history


for i in range(1, 52):
    add_message("user", f"Message {i}", "fastapi.pdf")

print(get_history())
print(len(get_history()))