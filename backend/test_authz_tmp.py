from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router

app = FastAPI()
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api")

client = TestClient(app)

# Login analista
r = client.post('/api/v1/auth/login', json={'email':'analista.prueba@dominio.com','password':'PasswordValido123*'})
print('analista login:', r.status_code)
token_analista = r.json()['access_token']

# Analista intenta acceder a endpoint admin
r2 = client.post('/api/admin/etl', headers={'Authorization': f'Bearer {token_analista}'})
print('analista -> /api/admin/etl:', r2.status_code)  # debe ser 403

# Login admin
r3 = client.post('/api/v1/auth/login', json={'email':'usuario.prueba@dominio.com','password':'PasswordValido123*'})
print('admin login:', r3.status_code)
token_admin = r3.json()['access_token']

# Admin accede correctamente
r4 = client.post('/api/admin/etl', headers={'Authorization': f'Bearer {token_admin}'})
print('admin -> /api/admin/etl:', r4.status_code)  # debe ser 200

# Token alterado/malformado
r5 = client.post('/api/admin/etl', headers={'Authorization': 'Bearer abc.def.ghi'})
print('bad token:', r5.status_code)  # debe ser 401
