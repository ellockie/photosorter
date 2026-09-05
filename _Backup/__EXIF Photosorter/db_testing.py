import sqlite3


db_path = "_DataBase\cameras_times_locations.sqlite"
conn = sqlite3.connect(db_path)

# db testing
cursor = conn.cursor()

cursor.execute("create table if not exists stocksu(i, symbol varchar)")
t = ('RHAT',)
cursor.execute('SELECT * FROM stocksu WHERE symbol=?', t)
print(cursor.fetchone())

# Larger example that inserts many records at a time
purchases = [
	('2006-03-28', 'BUY', 'IBM', 1000, 45.00),
	('2006-04-05', 'BUY', 'MSFT', 1000, 72.00),
	('2006-04-06', 'SELL', 'IBM', 500, 53.00),
]
cursor.executemany('INSERT INTO stocks VALUES (?,?,?,?,?)', purchases)

conn.close()