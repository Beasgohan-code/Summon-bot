import re

path = "main.py"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

if "log_custom_emojis" in src:
    print("ALREADY ADDED")
    exit()

# Find telegram.ext import block and add filters if missing
m = re.search(r"from telegram\.ext import \(([^\)]+)\)", src, re.DOTALL)
if m:
    block = m.group(1)
    if "filters" not in block:
        new_block = block.rstrip() + ",\n    filters,\n"
        src = src.replace(m.group(0), "from telegram.ext import (" + new_block + ")")
        print("Added filters to import")
else:
    # No parens, single line
    m2 = re.search(r"from telegram\.ext import (.+)", src)
    if m2 and "filters" not in m2.group(1):
        src = src.replace(m2.group(0), m2.group(0).rstrip() + ", filters")
        print("Added filters to single-line import")

# Insert handler before app.run_polling
new_code = '''    async def log_custom_emojis(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message and update.message.entities:
            for e in update.message.entities:
                if e.type == "custom_emoji":
                    ch = update.message.text[e.offset:e.offset+e.length]
                    with open("emoji_ids.txt", "a", encoding="utf-8") as f:
                        f.write(f"{ch} -> {e.custom_emoji_id}\\n")
                    print(f"LOGGED: {ch} -> {e.custom_emoji_id}")

    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, log_custom_emojis), group=10)

'''

src = src.replace("app.run_polling", new_code + "app.run_polling")
print("Added handler")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("DONE")

