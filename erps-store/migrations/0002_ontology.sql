CREATE TABLE erps.ontology_types(kind TEXT PRIMARY KEY,strong_attributes TEXT[] NOT NULL,description TEXT NOT NULL);
INSERT INTO erps.ontology_types VALUES
 ('Person',ARRAY['passport','national_id'],'Natural person'),
 ('Organisation',ARRAY['registration_id'],'Organisation'),
 ('Doi',ARRAY['doi'],'Digital object identifier'),
 ('Document',ARRAY['doi'],'Document'),
 ('Location',ARRAY[]::text[],'Location'),('Handle',ARRAY[]::text[],'Public handle'),
 ('Email',ARRAY[]::text[],'Email address'),('Phone',ARRAY[]::text[],'Telephone number'),
 ('Patent',ARRAY[]::text[],'Patent identifier'),('Date',ARRAY[]::text[],'Date mention');
