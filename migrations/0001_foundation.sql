-- Initial additive PostgreSQL schema; private bootstrap credentials are created separately.

CREATE TABLE IF NOT EXISTS audit_head (
	id SERIAL NOT NULL,
	digest VARCHAR(64) NOT NULL,
	PRIMARY KEY (id)
)

;

CREATE TABLE IF NOT EXISTS audit_log (
	id SERIAL NOT NULL,
	time TIMESTAMP WITH TIME ZONE NOT NULL,
	actor VARCHAR(64),
	action VARCHAR(80) NOT NULL,
	detail JSON NOT NULL,
	previous_hash VARCHAR(64) NOT NULL,
	entry_hash VARCHAR(64) NOT NULL,
	PRIMARY KEY (id)
)

;

CREATE TABLE IF NOT EXISTS cases (
	id VARCHAR(64) NOT NULL,
	name VARCHAR(200) NOT NULL,
	created TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id)
)

;

CREATE TABLE IF NOT EXISTS schema_version (
	version SERIAL NOT NULL,
	applied TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (version)
)

;

CREATE TABLE IF NOT EXISTS users (
	id VARCHAR(64) NOT NULL,
	username VARCHAR(64) NOT NULL,
	password_hash TEXT NOT NULL,
	role VARCHAR(16) NOT NULL,
	active BOOLEAN NOT NULL,
	totp_seed TEXT,
	totp_enabled BOOLEAN NOT NULL,
	totp_last_counter INTEGER NOT NULL,
	token_version INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (username)
)

;

CREATE TABLE IF NOT EXISTS collection_jobs (
	id VARCHAR(64) NOT NULL,
	case_id VARCHAR(64) NOT NULL,
	username VARCHAR(64) NOT NULL,
	authorisation TEXT NOT NULL,
	status VARCHAR(40) NOT NULL,
	updated TIMESTAMP WITH TIME ZONE NOT NULL,
	result JSON NOT NULL,
	error TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(case_id) REFERENCES cases (id)
)

;

CREATE TABLE IF NOT EXISTS entities (
	id VARCHAR(64) NOT NULL,
	case_id VARCHAR(64) NOT NULL,
	kind VARCHAR(40) NOT NULL,
	name VARCHAR(500) NOT NULL,
	data JSON NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(case_id) REFERENCES cases (id)
)

;

CREATE TABLE IF NOT EXISTS evidence_records (
	id VARCHAR(64) NOT NULL,
	case_id VARCHAR(64) NOT NULL,
	title TEXT NOT NULL,
	status VARCHAR(80) NOT NULL,
	sha256 VARCHAR(64),
	source_url TEXT NOT NULL,
	byte_size INTEGER NOT NULL,
	provenance JSON NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(case_id) REFERENCES cases (id)
)

;
