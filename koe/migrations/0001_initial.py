# Generated by Django 2.0.1 on 2018-02-01 11:37

from django.db import migrations, models
import django.db.models.deletion
import koe.models
import root.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AudioFile',
            fields=[
                ('id', models.CharField(editable=False, max_length=1024, primary_key=True, serialize=False)),
                ('raw_file', models.CharField(max_length=1024, unique=True)),
                ('mp3_file', models.CharField(max_length=1024, unique=True)),
                ('fs', models.IntegerField()),
                ('length', models.IntegerField()),
                ('name', models.CharField(max_length=1024)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model, root.models.AutoSetterGetterMixin),
        ),
        migrations.CreateModel(
            name='AudioTrack',
            fields=[
                ('id', models.CharField(editable=False, max_length=1024, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=1024)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model, root.models.AutoSetterGetterMixin),
        ),
        migrations.CreateModel(
            name='DistanceMatrix',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ids', koe.models.NumpyArrayField()),
                ('triu', koe.models.NumpyArrayField()),
                ('chksum', models.CharField(max_length=8)),
                ('algorithm', models.CharField(max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='Segment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_time_ms', models.IntegerField()),
                ('end_time_ms', models.IntegerField()),
            ],
            options={
                'ordering': ('segmentation', 'start_time_ms'),
            },
            bases=(models.Model, root.models.AutoSetterGetterMixin),
        ),
        migrations.CreateModel(
            name='Segmentation',
            fields=[
                ('id', models.CharField(editable=False, max_length=1024, primary_key=True, serialize=False)),
                ('source', models.CharField(max_length=1023)),
                ('audio_file', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='koe.AudioFile')),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model, root.models.AutoSetterGetterMixin),
        ),
        migrations.AddField(
            model_name='segment',
            name='segmentation',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='koe.Segmentation'),
        ),
        migrations.AlterUniqueTogether(
            name='distancematrix',
            unique_together={('chksum', 'algorithm')},
        ),
        migrations.AddField(
            model_name='audiofile',
            name='track',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.CASCADE, to='koe.AudioTrack'),
        ),
    ]
