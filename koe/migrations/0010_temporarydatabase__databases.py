# Generated by Django 2.0.4 on 2018-10-02 20:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('koe', '0009_auto_20181002_0846'),
    ]

    operations = [
        migrations.AddField(
            model_name='temporarydatabase',
            name='_databases',
            field=models.CharField(max_length=255, null=True),
        ),
    ]