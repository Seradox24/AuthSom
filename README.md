# AuthSom

Proveedor de identidad OpenID Connect con Keycloak 26.7.5 y PostgreSQL 17.
El proyecto contiene el servicio y su configuración inicial; puede instalarse
con Docker Compose en cualquier host compatible, sin editar los archivos del repositorio.

## Inicio en producción

1. Copiar `.env.example` a `.env` y definir las URL y secretos reales.
2. Validar con `docker compose config --quiet` (no muestra secretos).
3. Ejecutar `docker compose up -d --wait --wait-timeout 300`.
4. Revisar `docker compose ps` y `docker compose logs keycloak`.

Se utiliza `start --import-realm`, con PostgreSQL persistente. El puerto HTTP
se publica en loopback por defecto; el puerto de salud 9000 y PostgreSQL
permanecen dentro de la red del proyecto.

La URL pública `KEYCLOAK_HOSTNAME` debe ser HTTPS. El despliegue necesita un
proxy que termine TLS y sobrescriba las cabeceras de reenvío. DNS, certificados,
Nginx y rutas del servidor se configuran en la infraestructura de cada entorno.
Por defecto se esperan cabeceras `X-Forwarded-*`; puede seleccionarse `forwarded`
con `KEYCLOAK_PROXY_HEADERS` si el proxy utiliza esa cabecera.

## Configuración inicial

| Variable | Uso |
| --- | --- |
| `KEYCLOAK_HOSTNAME` | URL pública HTTPS del SSO, sin barra final |
| `KEYCLOAK_ADMIN_USERNAME`, `KEYCLOAK_ADMIN_PASSWORD` | Administrador inicial del realm master |
| `KEYCLOAK_DB_PASSWORD` | Contraseña de la base de datos |
| `MOODLE_BASE_URL`, `MOODLE_OIDC_CLIENT_SECRET` | URL y secreto del cliente Moodle |
| `KEYCLOAK_DB_NAME`, `KEYCLOAK_DB_USER` | Opcionales; valor predeterminado keycloak |
| `KEYCLOAK_BIND_ADDRESS`, `KEYCLOAK_HTTP_PORT` | Opcionales; valores predeterminados 127.0.0.1 y 8080 |
| `KEYCLOAK_PROXY_HEADERS` | Opcional; valor predeterminado xforwarded |

Los secretos no se versionan. Proteger `.env` con permisos restrictivos en el host.
Los valores del ejemplo deben sustituirse antes de arrancar.

## Realm y clientes

Se importa `educacion` con cuatro clientes: `moodle`, `flutter-desktop`,
`web-login` y `lrs-bridge`. No incluye usuarios de demostración.
Moodle usa un cliente confidencial con secreto, compatible con OAuth 2 estándar
de Moodle 5.2. Los clientes públicos utilizan PKCE S256.

`web-login` conserva URL localhost para desarrollo; registrar las URL exactas de
la aplicación al integrarla en producción. La recuperación de contraseña requiere
configurar SMTP en Keycloak.

La importación solo crea un realm que todavía no existe. Cambiar el JSON o las
variables de Moodle después del primer arranque no actualiza el realm existente:
los cambios posteriores se realizan con la administración o API de Keycloak.
Las credenciales bootstrap también se aplican en la inicialización, y cambiar la
contraseña PostgreSQL en `.env` no cambia la contraseña de una base ya creada.

## Persistencia y operación

Compose administra los nombres de contenedores, red y volumen bajo el proyecto
`authsom`. Para varias instalaciones puede usarse `docker compose -p <nombre>`
y un puerto diferente. Cada instalación conserva su propio volumen.

- `docker compose stop`: detiene los servicios conservando datos.
- `docker compose down`: retira contenedores y red, conservando el volumen.
- `docker compose down --volumes`: elimina la base de datos; evitar en producción.

Respaldar PostgreSQL antes de actualizar. No cambiar el nombre de proyecto de
una instalación existente sin planificar la migración del volumen.

Rutas y comprobaciones: ver `ACCESO.md`.
