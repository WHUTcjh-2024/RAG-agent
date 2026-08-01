create table body_profiles (
    user_id uuid primary key,
    chest_cm numeric(6, 2),
    updated_at timestamp with time zone not null
);

create table product_sku_facts (
    product_id varchar(128) primary key,
    sku_id varchar(128) not null,
    size varchar(32),
    chest_cm numeric(6, 2),
    price numeric(19, 2),
    in_stock boolean,
    return_policy varchar(500),
    version varchar(128) not null,
    updated_at timestamp with time zone not null
);
