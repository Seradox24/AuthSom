# Acceso a AuthSom

Todas las rutas públicas parten de `KEYCLOAK_HOSTNAME`, definido en `.env`.
Keycloak 26 no utiliza el prefijo `/auth`.

| Recurso | Ruta |
| --- | --- |
| Administración | `/admin/` |
| Cuenta de usuario | `/realms/educacion/account` |
| Discovery OIDC | `/realms/educacion/.well-known/openid-configuration` |
| JWKS | `/realms/educacion/protocol/openid-connect/certs` |
| Token | `/realms/educacion/protocol/openid-connect/token` |
| Logout | `/realms/educacion/protocol/openid-connect/logout` |

El administrador inicial pertenece al realm `master` y utiliza las credenciales
bootstrap definidas en `.env`. Los usuarios del realm `educacion` se crean desde
la administración; no se importan cuentas de ejemplo.

## Clientes

| Cliente | Tipo | Retorno inicial |
| --- | --- | --- |
| `moodle` | Confidencial, con secreto | `${MOODLE_BASE_URL}/admin/oauth2callback.php` |
| `flutter-desktop` | Público, PKCE S256 | `http://localhost:14100/callback`, `http://127.0.0.1:14100/callback` |
| `web-login` | Público, PKCE S256 | `http://localhost:3000/callback` |
| `lrs-bridge` | Bearer-only | Ninguno |

En Moodle configurar un proveedor OpenID Connect con base
`<KEYCLOAK_HOSTNAME>/realms/educacion`, client ID `moodle` y el secreto inicial
`MOODLE_OIDC_CLIENT_SECRET`; habilitar la autenticación OAuth 2 y verificar
los mapeos de nombre, apellido y correo.

## Verificación

```bash
docker compose ps
docker compose logs --tail 100 keycloak
docker compose exec keycloak bash -ec 'exec 3<>/dev/tcp/127.0.0.1/9000; printf "GET /health/ready HTTP/1.0\r\nHost: localhost\r\n\r\n" >&3; cat <&3'
```

El healthcheck debe quedar healthy. Consultar el discovery mediante la URL
pública y comprobar que el issuer sea `<KEYCLOAK_HOSTNAME>/realms/educacion`.
Con el puerto predeterminado también puede consultarse desde el host:

```bash
curl --fail http://127.0.0.1:8080/realms/educacion/.well-known/openid-configuration
```

El endpoint de salud usa el puerto 9000 interno, sin publicación en el host.
El acceso público requiere TLS y proxy configurados por el entorno.
