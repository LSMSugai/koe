# Generated by Django 2.0.1 on 2018-05-03 05:47

from django.db import migrations, models
import django.db.models.deletion
import root.models


class Migration(migrations.Migration):

    dependencies = [
        ('koe', '0010_auto_20180314_0842'),
    ]

    operations = [
        migrations.CreateModel(
            name='Species',
            fields=[
                ('id', models.CharField(editable=False, max_length=255, primary_key=True, serialize=False)),
                ('genus', models.CharField(max_length=32)),
                ('species', models.CharField(max_length=32)),
            ],
            bases=(models.Model, root.models.AutoSetterGetterMixin),
        ),
        migrations.AlterField(
            model_name='databaseassignment',
            name='permission',
            field=models.IntegerField(choices=[(1, 'View'), (2, 'Annotate'), (3, 'Add Files'), (4, 'Delete Files'), (10, 'Assign User')]),
        ),
        migrations.AlterUniqueTogether(
            name='species',
            unique_together={('species', 'genus')},
        ),
        migrations.AddField(
            model_name='individual',
            name='species',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='koe.Species'),
        ),
        migrations.AlterUniqueTogether(
            name='individual',
            unique_together={('name', 'species')},
        ),
    ]