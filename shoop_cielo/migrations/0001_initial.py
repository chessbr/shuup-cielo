# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import enumfields.fields
import shoop.core.fields
import shoop_cielo.constants
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('shoop', '0023_add_shipment_identifier'),
    ]

    operations = [
        migrations.CreateModel(
            name='CieloInstallmentInterestBehaviorComponent',
            fields=[
                ('servicebehaviorcomponent_ptr', models.OneToOneField(to='shoop.ServiceBehaviorComponent', parent_link=True, serialize=False, primary_key=True, auto_created=True)),
            ],
            options={
                'abstract': False,
            },
            bases=('shoop.servicebehaviorcomponent',),
        ),
        migrations.CreateModel(
            name='CieloWS15PaymentProcessor',
            fields=[
                ('paymentprocessor_ptr', models.OneToOneField(to='shoop.PaymentProcessor', parent_link=True, serialize=False, primary_key=True, auto_created=True)),
                ('ec_num', models.CharField(verbose_name="Cielo's affiliation number", max_length=20)),
                ('ec_key', models.CharField(verbose_name="Cielo's affiliation secret key", max_length=100)),
                ('auto_capture', models.BooleanField(verbose_name='Auto capture transactions', help_text='Enable this to capture transactions right after they get approved.', default=False)),
                ('authorization_mode', models.SmallIntegerField(verbose_name='Authorization mode', help_text='Select the authroization type for credit cards.', default=2, choices=[(0, 'Only authenticate'), (1, 'Only if the transaction gets authenticated'), (2, 'If the transaction gets athenticated or not'), (3, 'Direct, do not authenticate'), (4, 'Recurrent')])),
                ('max_installments', models.PositiveSmallIntegerField(verbose_name='Maximun installments number', default=1, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(18)])),
                ('installments_without_interest', models.PositiveSmallIntegerField(verbose_name='Installments without interest', help_text='How many installments will have no interest applied.', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(18)], default=1)),
                ('interest_type', models.CharField(verbose_name='Interest type', default='P', max_length=1, choices=[('S', 'Simple'), ('P', 'PRICE table')])),
                ('interest_rate', models.DecimalField(max_digits=5, verbose_name='Interest rate', default=Decimal('0'), validators=[django.core.validators.MinValueValidator(Decimal('0'))], decimal_places=2)),
                ('min_installment_amount', models.DecimalField(max_digits=9, verbose_name='Minimum installment amount', default=Decimal('5'), validators=[django.core.validators.MinValueValidator(Decimal('5'))], decimal_places=2)),
                ('sandbox', models.BooleanField(verbose_name='Sandbox mode', help_text='Enable this to activate Developer mode (test mode).', default=False)),
            ],
            options={
                'verbose_name_plural': 'Cielo Webservice v1.5',
                'verbose_name': 'Cielo Webservice v1.5',
            },
            bases=('shoop.paymentprocessor',),
        ),
        migrations.CreateModel(
            name='CieloWS15Transaction',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('tid', models.CharField(verbose_name='Transaction ID', max_length=50)),
                ('status', enumfields.fields.EnumIntegerField(blank=True, verbose_name='Transaction status', default=0, enum=shoop_cielo.constants.CieloTransactionStatus)),
                ('creation_date', models.DateTimeField(auto_now_add=True, verbose_name='Creation date')),
                ('last_update', models.DateTimeField(verbose_name='Last update', auto_now=True)),
                ('cc_holder', models.CharField(verbose_name='Card holder', max_length=50)),
                ('cc_brand', models.CharField(verbose_name='Card brand', max_length=30)),
                ('installments', models.PositiveSmallIntegerField(verbose_name='Installments', default=1)),
                ('cc_product', models.CharField(verbose_name='Product', choices=[('1', 'Credit'), ('2', 'Installment credit'), ('A', 'Debit')], max_length=30)),
                ('total_value', shoop.core.fields.MoneyValueField(max_digits=36, editable=False, default=0, verbose_name='transaction total', decimal_places=9)),
                ('total_captured_value', shoop.core.fields.MoneyValueField(max_digits=36, verbose_name='total captured', default=0, decimal_places=9)),
                ('total_reversed_value', shoop.core.fields.MoneyValueField(max_digits=36, verbose_name='total reversed', default=0, decimal_places=9)),
                ('authorization_lr', models.CharField(blank=True, verbose_name='Authorization LR code', max_length=2)),
                ('authorization_nsu', models.CharField(blank=True, null=True, verbose_name='Authorization NSU', max_length=50)),
                ('authorization_date', models.DateTimeField(blank=True, null=True, verbose_name='Authorization date')),
                ('authentication_eci', models.SmallIntegerField(null=True, verbose_name='ECI security level', default=0)),
                ('authentication_date', models.DateTimeField(blank=True, null=True, verbose_name='Authentication date')),
                ('order', models.ForeignKey(related_name='cielows15_transactions', verbose_name='Order', to='shoop.Order')),
            ],
            options={
                'verbose_name_plural': 'Cielo 1.5 transactions',
                'verbose_name': 'Cielo 1.5 transaction',
            },
        ),
    ]
