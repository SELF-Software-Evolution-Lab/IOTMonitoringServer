from django.db import migrations

# Migraciones para configuración de la base de datos Postgres con la extensión de Timescale.


class Migration(migrations.Migration):

    dependencies = [
        ("receiver", "0001_initial"),
    ]

    operations = [
        # Crea la hipertabla de timescale con chunks de 3 días.
        migrations.RunSQL(
            "SELECT create_hypertable('\"receiver_data\"', 'time', chunk_time_interval=>259200000000);"
        ),
        # Configura la compresión para estaciones y variables. Son llaves foráneas de la tabla principal.
        migrations.RunSQL(
            "ALTER TABLE \"receiver_data\" \
                SET (timescaledb.compress, \
                timescaledb.compress_segmentby = 'station_id, measurement_id, base_time');"
        ),
        # Comprime los datos cada 7 días.
        migrations.RunSQL(
            "SELECT add_compression_policy('\"receiver_data\"', 604800000000);"
        ),
    ]
