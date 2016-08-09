# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shuup', '0004_update_orderline_refunds'),
        ('shuup_cielo', '0002_auto_20160627_2257'),
    ]

    operations = [
        migrations.CreateModel(
            name='DiscountPercentageBehaviorComponent',
            fields=[
                ('servicebehaviorcomponent_ptr', models.OneToOneField(primary_key=True, auto_created=True, serialize=False, to='shuup.ServiceBehaviorComponent', parent_link=True)),
                ('percentage', models.DecimalField(decimal_places=2, verbose_name='Discount percentage', max_digits=5)),
            ],
            options={
                'abstract': False,
            },
            bases=('shuup.servicebehaviorcomponent',),
        ),
    ]
