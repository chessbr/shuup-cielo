# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('shoop_cielo', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cielows15paymentprocessor',
            name='authorization_mode',
            field=models.SmallIntegerField(default=2, help_text='Select the authroization type for credit cards.', choices=[(0, 'Only authenticate'), (1, 'Only if the transaction gets authenticated'), (2, 'If the transaction gets authenticated or not'), (3, 'Direct, do not authenticate'), (4, 'Recurrent')], verbose_name='Authorization mode'),
        ),
        migrations.AlterField(
            model_name='cielows15paymentprocessor',
            name='max_installments',
            field=models.PositiveSmallIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(18)], verbose_name='Maximum installments number'),
        ),
    ]
