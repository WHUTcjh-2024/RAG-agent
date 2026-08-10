alter table product_sku_facts add column source_kind varchar(32) not null default 'MERCHANT_FEED';
alter table product_sku_facts add column source_reference varchar(255) not null default 'catalog:legacy';
alter table product_sku_facts add column source_confidence numeric(3, 2) not null default 0.95;
