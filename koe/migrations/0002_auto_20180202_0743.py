# Generated by Django 2.0.1 on 2018-02-01 18:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('koe', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='distancematrix',
            name='id',
            field=models.CharField(editable=False, max_length=1024, primary_key=True, serialize=False),
        ),
    ]
