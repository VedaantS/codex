--
-- PostgreSQL database dump
--

-- Dumped from database version 15.10 (Homebrew)
-- Dumped by pg_dump version 15.10 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: app_status_enum; Type: TYPE; Schema: public; Owner: vedaantsrivastava
--

CREATE TYPE public.app_status_enum AS ENUM (
    'pending',
    'shortlisted',
    'awarded',
    'rejected'
);


ALTER TYPE public.app_status_enum OWNER TO vedaantsrivastava;

--
-- Name: role_enum; Type: TYPE; Schema: public; Owner: vedaantsrivastava
--

CREATE TYPE public.role_enum AS ENUM (
    'scientist',
    'funder',
    'admin'
);


ALTER TYPE public.role_enum OWNER TO vedaantsrivastava;

--
-- Name: visibility_enum; Type: TYPE; Schema: public; Owner: vedaantsrivastava
--

CREATE TYPE public.visibility_enum AS ENUM (
    'public',
    'collaborators_only',
    'private'
);


ALTER TYPE public.visibility_enum OWNER TO vedaantsrivastava;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: awards; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.awards (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    application_id uuid NOT NULL,
    awarded_amount numeric(15,2) NOT NULL,
    awarded_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.awards OWNER TO vedaantsrivastava;

--
-- Name: chat_channels; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.chat_channels (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    experiment_id uuid NOT NULL,
    name character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.chat_channels OWNER TO vedaantsrivastava;

--
-- Name: chat_messages; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.chat_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    channel_id uuid NOT NULL,
    sender_id uuid NOT NULL,
    content text NOT NULL,
    sent_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.chat_messages OWNER TO vedaantsrivastava;

--
-- Name: collaboration_suggestions; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.collaboration_suggestions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    for_user_id uuid NOT NULL,
    suggested_user_id uuid NOT NULL,
    reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.collaboration_suggestions OWNER TO vedaantsrivastava;

--
-- Name: discovery_items; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.discovery_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    field character varying(100),
    status character varying(100),
    lead_name character varying(255),
    tags text[],
    ai_score double precision,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.discovery_items OWNER TO vedaantsrivastava;

--
-- Name: experiment_steps; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.experiment_steps (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    protocol_version_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    content_markdown text,
    estimated_time_minutes integer,
    assigned_to_id uuid,
    reproducibility_score double precision,
    impact_score double precision,
    difficulty_score double precision,
    order_index integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    due_date date,
    done boolean DEFAULT false,
    results_markdown text,
    node_type character varying(32) DEFAULT 'step'::character varying
);


ALTER TABLE public.experiment_steps OWNER TO vedaantsrivastava;

--
-- Name: experiments; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.experiments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    owner_id uuid NOT NULL,
    visibility public.visibility_enum DEFAULT 'private'::public.visibility_enum NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.experiments OWNER TO vedaantsrivastava;

--
-- Name: file_attachments; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.file_attachments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    owner_id uuid NOT NULL,
    experiment_step_id uuid NOT NULL,
    filename character varying(255) NOT NULL,
    storage_path text NOT NULL,
    mime_type character varying(100),
    size_bytes bigint,
    uploaded_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.file_attachments OWNER TO vedaantsrivastava;

--
-- Name: global_chat_messages; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.global_chat_messages (
    id uuid NOT NULL,
    sender_id uuid NOT NULL,
    recipient_id uuid NOT NULL,
    content text NOT NULL,
    sent_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.global_chat_messages OWNER TO vedaantsrivastava;

--
-- Name: grant_applications; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.grant_applications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    grant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    answers jsonb,
    status public.app_status_enum DEFAULT 'pending'::public.app_status_enum NOT NULL,
    submitted_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.grant_applications OWNER TO vedaantsrivastava;

--
-- Name: grant_milestones; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.grant_milestones (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    award_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    due_date date,
    completed boolean DEFAULT false NOT NULL,
    completed_at timestamp with time zone
);


ALTER TABLE public.grant_milestones OWNER TO vedaantsrivastava;

--
-- Name: grants; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.grants (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    total_funding_usd numeric(15,2),
    application_questions text[],
    created_by_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.grants OWNER TO vedaantsrivastava;

--
-- Name: lab_members; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.lab_members (
    lab_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role character varying(50) DEFAULT 'member'::character varying,
    joined_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.lab_members OWNER TO vedaantsrivastava;

--
-- Name: labs; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.labs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    affiliation character varying(255),
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.labs OWNER TO vedaantsrivastava;

--
-- Name: notebook_attachments; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.notebook_attachments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    entry_id uuid,
    filename character varying(255),
    storage_path character varying(255),
    uploaded_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.notebook_attachments OWNER TO vedaantsrivastava;

--
-- Name: notebook_entries; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.notebook_entries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    user_id uuid,
    user_name character varying(255),
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    device character varying(255),
    location character varying(255),
    session_id character varying(255),
    experiment_id character varying(255),
    version character varying(50),
    visibility character varying(50) DEFAULT 'team'::character varying,
    content text,
    structured jsonb,
    diffs jsonb
);


ALTER TABLE public.notebook_entries OWNER TO vedaantsrivastava;

--
-- Name: profiles; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.profiles (
    user_id uuid NOT NULL,
    bio text,
    affiliation character varying(255),
    expertise_tags text[]
);


ALTER TABLE public.profiles OWNER TO vedaantsrivastava;

--
-- Name: projects; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    owner_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    budget_requested numeric(15,2),
    reproducibility_score double precision,
    impact_score double precision,
    difficulty_score double precision,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    paper_content text
);


ALTER TABLE public.projects OWNER TO vedaantsrivastava;

--
-- Name: protocol_versions; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.protocol_versions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    experiment_id uuid NOT NULL,
    version_label character varying(50) NOT NULL,
    parent_version_id uuid,
    metadata_ jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    step_map jsonb
);


ALTER TABLE public.protocol_versions OWNER TO vedaantsrivastava;

--
-- Name: users; Type: TABLE; Schema: public; Owner: vedaantsrivastava
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    role public.role_enum NOT NULL,
    avatar_url text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.users OWNER TO vedaantsrivastava;

--
-- Name: awards awards_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.awards
    ADD CONSTRAINT awards_pkey PRIMARY KEY (id);


--
-- Name: chat_channels chat_channels_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.chat_channels
    ADD CONSTRAINT chat_channels_pkey PRIMARY KEY (id);


--
-- Name: chat_messages chat_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_pkey PRIMARY KEY (id);


--
-- Name: collaboration_suggestions collaboration_suggestions_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.collaboration_suggestions
    ADD CONSTRAINT collaboration_suggestions_pkey PRIMARY KEY (id);


--
-- Name: discovery_items discovery_items_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.discovery_items
    ADD CONSTRAINT discovery_items_pkey PRIMARY KEY (id);


--
-- Name: experiment_steps experiment_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.experiment_steps
    ADD CONSTRAINT experiment_steps_pkey PRIMARY KEY (id);


--
-- Name: experiments experiments_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.experiments
    ADD CONSTRAINT experiments_pkey PRIMARY KEY (id);


--
-- Name: file_attachments file_attachments_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.file_attachments
    ADD CONSTRAINT file_attachments_pkey PRIMARY KEY (id);


--
-- Name: global_chat_messages global_chat_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.global_chat_messages
    ADD CONSTRAINT global_chat_messages_pkey PRIMARY KEY (id);


--
-- Name: grant_applications grant_applications_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.grant_applications
    ADD CONSTRAINT grant_applications_pkey PRIMARY KEY (id);


--
-- Name: grant_milestones grant_milestones_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.grant_milestones
    ADD CONSTRAINT grant_milestones_pkey PRIMARY KEY (id);


--
-- Name: grants grants_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.grants
    ADD CONSTRAINT grants_pkey PRIMARY KEY (id);


--
-- Name: lab_members lab_members_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.lab_members
    ADD CONSTRAINT lab_members_pkey PRIMARY KEY (lab_id, user_id);


--
-- Name: labs labs_name_key; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.labs
    ADD CONSTRAINT labs_name_key UNIQUE (name);


--
-- Name: labs labs_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.labs
    ADD CONSTRAINT labs_pkey PRIMARY KEY (id);


--
-- Name: notebook_attachments notebook_attachments_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.notebook_attachments
    ADD CONSTRAINT notebook_attachments_pkey PRIMARY KEY (id);


--
-- Name: notebook_entries notebook_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.notebook_entries
    ADD CONSTRAINT notebook_entries_pkey PRIMARY KEY (id);


--
-- Name: profiles profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.profiles
    ADD CONSTRAINT profiles_pkey PRIMARY KEY (user_id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: protocol_versions protocol_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.protocol_versions
    ADD CONSTRAINT protocol_versions_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_lab_members_user_id; Type: INDEX; Schema: public; Owner: vedaantsrivastava
--

CREATE INDEX idx_lab_members_user_id ON public.lab_members USING btree (user_id);


--
-- Name: awards awards_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.awards
    ADD CONSTRAINT awards_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.grant_applications(id) ON DELETE CASCADE;


--
-- Name: chat_channels chat_channels_experiment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.chat_channels
    ADD CONSTRAINT chat_channels_experiment_id_fkey FOREIGN KEY (experiment_id) REFERENCES public.experiments(id) ON DELETE CASCADE;


--
-- Name: chat_messages chat_messages_channel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.chat_channels(id) ON DELETE CASCADE;


--
-- Name: chat_messages chat_messages_sender_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: collaboration_suggestions collaboration_suggestions_for_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.collaboration_suggestions
    ADD CONSTRAINT collaboration_suggestions_for_user_id_fkey FOREIGN KEY (for_user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: collaboration_suggestions collaboration_suggestions_suggested_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.collaboration_suggestions
    ADD CONSTRAINT collaboration_suggestions_suggested_user_id_fkey FOREIGN KEY (suggested_user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: experiment_steps experiment_steps_assigned_to_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.experiment_steps
    ADD CONSTRAINT experiment_steps_assigned_to_id_fkey FOREIGN KEY (assigned_to_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: experiment_steps experiment_steps_protocol_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.experiment_steps
    ADD CONSTRAINT experiment_steps_protocol_version_id_fkey FOREIGN KEY (protocol_version_id) REFERENCES public.protocol_versions(id) ON DELETE CASCADE;


--
-- Name: experiments experiments_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.experiments
    ADD CONSTRAINT experiments_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: file_attachments file_attachments_experiment_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.file_attachments
    ADD CONSTRAINT file_attachments_experiment_step_id_fkey FOREIGN KEY (experiment_step_id) REFERENCES public.experiment_steps(id) ON DELETE CASCADE;


--
-- Name: file_attachments file_attachments_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.file_attachments
    ADD CONSTRAINT file_attachments_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: global_chat_messages global_chat_messages_recipient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.global_chat_messages
    ADD CONSTRAINT global_chat_messages_recipient_id_fkey FOREIGN KEY (recipient_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: global_chat_messages global_chat_messages_sender_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.global_chat_messages
    ADD CONSTRAINT global_chat_messages_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: grant_applications grant_applications_grant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.grant_applications
    ADD CONSTRAINT grant_applications_grant_id_fkey FOREIGN KEY (grant_id) REFERENCES public.grants(id) ON DELETE CASCADE;


--
-- Name: grant_applications grant_applications_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.grant_applications
    ADD CONSTRAINT grant_applications_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: grant_milestones grant_milestones_award_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.grant_milestones
    ADD CONSTRAINT grant_milestones_award_id_fkey FOREIGN KEY (award_id) REFERENCES public.awards(id) ON DELETE CASCADE;


--
-- Name: grants grants_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.grants
    ADD CONSTRAINT grants_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: lab_members lab_members_lab_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.lab_members
    ADD CONSTRAINT lab_members_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id) ON DELETE CASCADE;


--
-- Name: lab_members lab_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.lab_members
    ADD CONSTRAINT lab_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: labs labs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.labs
    ADD CONSTRAINT labs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: notebook_attachments notebook_attachments_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.notebook_attachments
    ADD CONSTRAINT notebook_attachments_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.notebook_entries(id) ON DELETE CASCADE;


--
-- Name: notebook_entries notebook_entries_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.notebook_entries
    ADD CONSTRAINT notebook_entries_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: notebook_entries notebook_entries_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.notebook_entries
    ADD CONSTRAINT notebook_entries_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: profiles profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.profiles
    ADD CONSTRAINT profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: projects projects_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: protocol_versions protocol_versions_experiment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.protocol_versions
    ADD CONSTRAINT protocol_versions_experiment_id_fkey FOREIGN KEY (experiment_id) REFERENCES public.experiments(id) ON DELETE CASCADE;


--
-- Name: protocol_versions protocol_versions_parent_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vedaantsrivastava
--

ALTER TABLE ONLY public.protocol_versions
    ADD CONSTRAINT protocol_versions_parent_version_id_fkey FOREIGN KEY (parent_version_id) REFERENCES public.protocol_versions(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

