# Instalación STT verificada — 29 de octubre de 2026

Destino: auth.minayao.site, realm educacion, Compose stt-authsom-prod.
Servicio independiente, sin habilitar SSO en Moodle ni otras aplicaciones.

- Keycloak 26.7.5 y PostgreSQL 17.11-alpine3.24 oficiales por digest del perfil.
- Dos perfiles aislados y cinco rechazos válidos; bootstrap presente solo en
  inicialización y completamente ausente después. No se crean contenedores
  durante la comprobación de perfiles.
- Administrador permanente stt-admin en master verificado por HTTPS. Cuenta
  temporal eliminada; credenciales bootstrap retiradas de archivos y entorno.
- Issuer exacto, discovery, JWKS, rechazo de administración anónima y cinco
  clientes deshabilitados comprobados. Persistencia verificada al recrear
  Keycloak sin bootstrap y al reiniciarlo durante el respaldo.
- Backend publicado únicamente en 127.0.0.1:18081. PostgreSQL y 9000 internos.
- Certificado público válido, HTTP→HTTPS y renovación simulada con recarga
  Nginx correctos. La configuración corresponde al vhost propio.
- Respaldo consistente 20261029_150834, checksums correctos, restaurado con la
  misma contraseña administrativa, realm, clientes y JWKS en red internal sin
  puertos publicados. Contenedores, red y archivos temporales retirados.
- Timer stt-authsom-prod-backup.timer a las 04:35 America/Santiago, siete
  copias completas; journal propio ante fallos. Copia externa pendiente.
- Secretos locales en la carpeta privada Credenciales-STT del propietario,
  con ACL restrictivas; operativos bajo secretos/authsom/prod, root0700/0600.
- VPS sin remoto/token GitHub para este servicio; entrega por bundle revisado.

La primera comprobación de transición detectó que Keycloak rechaza bootstrap
con valores vacíos; se separó el overlay inicial y se añadió regresión del
modelo Compose. No se cambiaron contraseñas ni datos al corregirlo.

SMTP pendiente; recuperación por correo deshabilitada. Los clientes conservan
sus identificadores pero no tienen redirecciones ni secretos importados.
Las notas históricas de auth_oidc describen otra instalación y no se aplicaron.

Runbook: STT_OPERACION.md. Evidencia privada del ensayo:
operaciones/registros/authsom/prod/restoration.json dentro de la raíz STT.
Esta fecha acredita las pruebas descritas, no monitoreo continuo ni una
auditoría exhaustiva de vulnerabilidades de las imágenes.
