# AuthSom independiente para STT

Variante `compose.stt.yaml`, seleccionada explícitamente; no combinar con el
Compose de desarrollo ni modificar una instalación anterior. La fuente incluye
el cliente launcher-windows de la rama existente. Los cinco clientes heredados
se conservan deshabilitados, sin secretos ni redirecciones activas.

## Perfil y consumidores

Copiar `.env.stt.example` a un perfil privado absoluto. `scripts/stt.py` lee ese
perfil y después `SECRET_ROOT/secrets.env`; rechaza claves duplicadas y variables
administradas exportadas. No ejecuta shell ni expande variables del archivo.
Compose recibe ambos archivos explícitos y el entorno validado, desde la raíz
del repositorio, con `-p COMPOSE_PROJECT_NAME` y `compose.stt.yaml`.

| Opción | Consumidor y aplicación |
| --- | --- |
| COMPOSE_PROJECT_NAME | Compose: identidad de red/contenedores al desplegar |
| KEYCLOAK_IMAGE, POSTGRES_IMAGE | Compose: imágenes por versión y digest |
| KEYCLOAK_HOSTNAME | KC_HOSTNAME al iniciar; Nginx al generar configuración |
| KEYCLOAK_HTTP_PORT | Puerto loopback de Compose y proxy Nginx |
| KEYCLOAK_DB_NAME, KEYCLOAK_DB_USER, KEYCLOAK_DB_PASSWORD | PostgreSQL inicial y conexión Keycloak; editar perfil no rota una BD existente |
| KEYCLOAK_ADMIN_USERNAME, KEYCLOAK_ADMIN_PASSWORD | Bootstrap temporal, solo primera inicialización; retirar después |
| KEYCLOAK_REALM, KEYCLOAK_REALM_DISPLAY_NAME | Generador del JSON inicial; editarlo no actualiza un realm existente |
| CONFIG_ROOT | JSON generado, montado en solo lectura, y perfil operativo |
| SECRET_ROOT | secrets.env y admin.json privados, nunca versionados |
| DATA_ROOT | Persistencia exclusiva de PostgreSQL bajo postgres/ |
| BACKUP_ROOT, BACKUP_KEEP | Copias completas con retención posterior a checksum correcto |

`secrets.env` contiene KEYCLOAK_DB_PASSWORD y temporalmente las dos opciones
bootstrap. `admin.json` contiene username/password de la cuenta permanente.
Directorio privado 0700 y archivos 0600. El import no contiene secretos y debe
ser legible por el UID de Keycloak; no publicar el directorio de configuración.

## Instalación y verificación

Revisar SHA y diff en rama/PR. Transferir bundle revisado a una VPS sin remoto ni
token GitHub. Clonar la rama main explícita o instalar el SHA revisado.
Crear rutas exclusivas con permisos de los UID necesarios. Ejecutar desde
cualquier directorio con ruta absoluta al script y perfil:

```sh
python3 scripts/stt.py --env-file /absolute/profile.env check
python3 scripts/stt.py --env-file /absolute/profile.env render
python3 scripts/stt.py --env-file /absolute/profile.env nginx
python3 scripts/stt.py --env-file /absolute/profile.env up
python3 scripts/admin.py --env-file /absolute/profile.env --initialize
```

Generar Nginx primero para ACME y luego con `nginx --tls`. Instalar únicamente el
virtual host propio, ejecutar nginx -t antes de recargar. Sobrescribir cabeceras
forwarded y mantener PostgreSQL/9000 internos; HTTP 8080 solo en loopback.
El admin inicial es temporal: crear permanente, asignar rol admin en master,
probar autenticación y eliminar temporal. Retirar variables bootstrap del archivo
privado y recrear solo Keycloak. El lanzador agrega `compose.bootstrap.yaml`
únicamente cuando existen ambas credenciales: al retirarlas omite por completo
las variables KC_BOOTSTRAP_ADMIN_*; no las envía vacías. `admin.py` sin
--initialize verifica sin mutar.
La consola pública requiere autenticación propia de Keycloak.

`scripts/test_profiles.py` comprueba dos modelos Compose sin arrancar contenedores
y rechazos de configuración. `admin.py` verifica issuer/JWKS, clientes
deshabilitados, administrador y ausencia de bootstrap. SMTP no configurado;
resetPasswordAllowed permanece false. No cambiar autenticación de Moodle.

Programar con `scripts/install_timer.py --env-file /absolute/profile.env
--calendar '*-*-* 04:35:00 America/Santiago'`. La unidad propia utiliza la ruta
del código instalado y el perfil explícito; otro calendario se selecciona como
parámetro. No reemplaza unidades diferentes sin revisión. Revisar fallos con
`journalctl -u <COMPOSE_PROJECT_NAME>-backup.service`.

## Respaldo, restauración y actualización

`stt.py ... backup` detiene únicamente Keycloak, produce pg_dump -Fc, archiva
configuración/secretos, imágenes, revisión y bundle completo; reinicia Keycloak
incluso ante error. Solo completa/retiene tras SHA256SUMS correcto. Los .partial
requieren investigación y no son copias completas. El dump incluye claves y
cuentas: todo el respaldo es privado. Timer propio con zona America/Santiago.

Para restaurar: verificar todos los checksums; recuperar el bundle y usar las
mismas imágenes. Extraer archivos solo en una raíz nueva, rechazando rutas
absolutas, ../ y enlaces; conservar el original. Crear otro proyecto, datos,
secretos y puerto loopback, e iniciar solo PostgreSQL. Restaurar con pg_restore
--exit-on-error --no-owner -U USUARIO -d BASE por stdin. Arrancar Keycloak sin
bootstrap y verificar cuenta, realm, clientes y JWKS. En ensayo sin puertos
publicados usar una red internal y docker exec para validar API/salud; no conectar
el proxy productivo. Retirar únicamente recursos identificados del ensayo.

Actualizar requiere respaldo y restauración probada, release/migraciones
revisadas, SHA y digest explícitos. No editar contenedores ni usar down -v.
Ante fallo de esquema, recuperar copia e imagen compatibles en raíz nueva y
cambiar el proxy después de verificar; bajar solo la imagen no revierte la BD.
Eliminar una instalación nueva fallida significa retirar su vhost y detener su
proyecto, conservando datos/secretos para diagnóstico. No modificar vecinos.

Referencias revisadas el 2026-10-29:
- https://www.keycloak.org/2026/09/keycloak-2675-released
- https://www.postgresql.org/support/security/
- https://www.keycloak.org/server/importExport
- https://www.keycloak.org/server/reverseproxy
- https://www.keycloak.org/server/bootstrap-admin-recovery
