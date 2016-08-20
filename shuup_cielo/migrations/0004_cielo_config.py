# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import shuup_cielo.constants
import enumfields.fields
import django.core.validators
import shuup.core.fields
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('shuup', '0004_update_orderline_refunds'),
        ('shuup_cielo', '0003_discountpercentagebehaviorcomponent'),
    ]

    operations = [
        migrations.CreateModel(
            name='CieloConfig',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', serialize=False, auto_created=True)),
                ('ec_num', models.CharField(max_length=20, verbose_name='Affiliation number')),
                ('ec_key', models.CharField(max_length=100, verbose_name='Affiliation secret key')),
                ('auto_capture', models.BooleanField(help_text='Enable this to capture transactions right after they get approved.', verbose_name='Auto capture transactions', default=False)),
                ('authorization_mode', models.SmallIntegerField(help_text='Select the authroization type for credit cards.', default=2, verbose_name='Authorization mode', choices=[(0, 'Only authenticate'), (1, 'Only if the transaction gets authenticated'), (2, 'If the transaction gets authenticated or not'), (3, 'Direct, do not authenticate'), (4, 'Recurrent')])),
                ('max_installments', models.PositiveSmallIntegerField(default=1, verbose_name='Maximum installments number', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)])),
                ('installments_without_interest', models.PositiveSmallIntegerField(help_text='How many installments will have no interest applied.', default=1, verbose_name='Installments without interest', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)])),
                ('interest_type', models.CharField(max_length=1, default='P', verbose_name='Interest type', choices=[('S', 'Simple'), ('P', 'PRICE table')])),
                ('interest_rate', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=5, verbose_name='Interest rate', validators=[django.core.validators.MinValueValidator(Decimal('0'))])),
                ('min_installment_amount', models.DecimalField(decimal_places=2, default=Decimal('5'), max_digits=9, verbose_name='Minimum installment amount', validators=[django.core.validators.MinValueValidator(Decimal('5'))])),
                ('sandbox', models.BooleanField(help_text='Enable this to activate Developer mode (test mode).', verbose_name='Sandbox mode', default=False)),
                ('shop', models.OneToOneField(verbose_name='Shop', to='shuup.Shop', related_name='cielo_config')),
            ],
            options={
                'verbose_name_plural': 'cielo configurations',
                'verbose_name': 'cielo configuration',
            },
        ),
        migrations.CreateModel(
            name='CieloOrderTransaction',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', serialize=False, auto_created=True)),
                ('order', models.ForeignKey(verbose_name='Order', null=True, default=None, to='shuup.Order', related_name='cielo_transactions')),
            ],
            options={
                'verbose_name_plural': 'Cielo pre-order transactions',
                'verbose_name': 'Cielo pre-order transaction',
            },
        ),
        migrations.CreateModel(
            name='CieloPaymentProcessor',
            fields=[
                ('paymentprocessor_ptr', models.OneToOneField(serialize=False, parent_link=True, to='shuup.PaymentProcessor', primary_key=True, auto_created=True)),
            ],
            options={
                'verbose_name_plural': 'Cielo',
                'verbose_name': 'Cielo',
            },
            bases=('shuup.paymentprocessor',),
        ),
        migrations.CreateModel(
            name='CieloTransaction',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', serialize=False, auto_created=True)),
                ('tid', models.CharField(max_length=50, verbose_name='Transaction ID')),
                ('status', enumfields.fields.EnumIntegerField(blank=True, enum=shuup_cielo.constants.CieloTransactionStatus, default=-1, verbose_name='Transaction status')),
                ('creation_date', models.DateTimeField(auto_now_add=True, verbose_name='Creation date')),
                ('last_update', models.DateTimeField(auto_now=True, verbose_name='Last update')),
                ('cc_holder', models.CharField(max_length=50, verbose_name='Card holder')),
                ('cc_brand', models.CharField(max_length=30, verbose_name='Card brand')),
                ('installments', models.PositiveSmallIntegerField(default=1, verbose_name='Installments')),
                ('cc_product', models.CharField(max_length=30, verbose_name='Product', choices=[('1', 'Credit'), ('2', 'Installment credit'), ('A', 'Debit')])),
                ('total_value', shuup.core.fields.MoneyValueField(decimal_places=9, default=0, max_digits=36, verbose_name='transaction total', editable=False)),
                ('total_captured_value', shuup.core.fields.MoneyValueField(default=0, max_digits=36, verbose_name='total captured', decimal_places=9)),
                ('total_reversed_value', shuup.core.fields.MoneyValueField(default=0, max_digits=36, verbose_name='total reversed', decimal_places=9)),
                ('interest_value', shuup.core.fields.MoneyValueField(decimal_places=9, default=0, max_digits=36, verbose_name='interest amount', editable=False)),
                ('authorization_lr', models.CharField(max_length=2, blank=True, verbose_name='Authorization LR code')),
                ('authorization_nsu', models.CharField(max_length=50, blank=True, verbose_name='Authorization NSU', null=True)),
                ('authorization_date', models.DateTimeField(null=True, blank=True, verbose_name='Authorization date')),
                ('authentication_eci', models.SmallIntegerField(null=True, default=0, verbose_name='ECI security level')),
                ('authentication_date', models.DateTimeField(null=True, blank=True, verbose_name='Authentication date')),
                ('international', models.BooleanField(verbose_name='International transaction', default=False)),
                ('order_transaction', models.OneToOneField(verbose_name='Cielo Order', to='shuup_cielo.CieloOrderTransaction', related_name='transaction')),
                ('shop', models.ForeignKey(to='shuup.Shop', verbose_name='shop')),
            ],
            options={
                'verbose_name_plural': 'Cielo 1.5 transactions',
                'verbose_name': 'Cielo 1.5 transaction',
            },
        ),
        migrations.RemoveField(
            model_name='cielows15paymentprocessor',
            name='paymentprocessor_ptr',
        ),
        migrations.RemoveField(
            model_name='cielows15transaction',
            name='order',
        ),
        migrations.DeleteModel(
            name='CieloWS15PaymentProcessor',
        ),
        migrations.DeleteModel(
            name='CieloWS15Transaction',
        ),
    ]
