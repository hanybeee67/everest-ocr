
import bcrypt

password = b"ev@7668850"
hashed = b"$2b$12$Kj5KSvJ3W.o7s6mKEabht.PLRuWPoJllo9TiYN/17UwvoMA8RIhke"

if bcrypt.checkpw(password, hashed):
    print("MATCH")
else:
    print("NO MATCH")
    # Generate new hash just in case
    new_hash = bcrypt.hashpw(password, bcrypt.gensalt(rounds=12))
    print(f"NEW HASH: {new_hash.decode()}")
