-- ==============================================================================
-- Migration Supabase : Tables profiles, parents, accountants, et students + RLS
-- ==============================================================================

-- 1. Extension pour les UUIDs (au cas où non active par défaut)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Énumération des rôles utilisateurs
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('ADMIN', 'COMPTABLE', 'PARENT');
    END IF;
END $$;

-- 3. Table `profiles` (liée à auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone TEXT,
    role user_role NOT NULL DEFAULT 'PARENT',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Table `parents`
CREATE TABLE IF NOT EXISTS public.parents (
    id UUID PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Table `accountants`
CREATE TABLE IF NOT EXISTS public.accountants (
    id UUID PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. Table `students`
CREATE TABLE IF NOT EXISTS public.students (
    id SERIAL PRIMARY KEY,
    matricule TEXT UNIQUE NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    parent_id UUID NOT NULL REFERENCES public.parents(id) ON DELETE CASCADE,
    class_id INT REFERENCES public.classes(id) ON DELETE SET NULL,
    class_name TEXT,
    school_year TEXT DEFAULT '2025-2026',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index pour accélérer les jointures
CREATE INDEX IF NOT EXISTS idx_students_parent_id ON public.students(parent_id);
CREATE INDEX IF NOT EXISTS idx_profiles_role ON public.profiles(role);

-- 7. Trigger automatique pour insérer dans `profiles` lors de la création d'un utilisateur dans auth.users
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, first_name, last_name, phone, role)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'first_name', ''),
        COALESCE(NEW.raw_user_meta_data->>'last_name', ''),
        NEW.raw_user_meta_data->>'phone',
        COALESCE((NEW.raw_user_meta_data->>'role')::public.user_role, 'PARENT'::public.user_role)
    )
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        first_name = EXCLUDED.first_name,
        last_name = EXCLUDED.last_name,
        phone = EXCLUDED.phone,
        role = EXCLUDED.role;

    -- Insertion spécifique selon le rôle
    IF (NEW.raw_user_meta_data->>'role') = 'PARENT' THEN
        INSERT INTO public.parents (id, first_name, last_name, email, phone)
        VALUES (
            NEW.id,
            COALESCE(NEW.raw_user_meta_data->>'first_name', ''),
            COALESCE(NEW.raw_user_meta_data->>'last_name', ''),
            NEW.email,
            NEW.raw_user_meta_data->>'phone'
        )
        ON CONFLICT (id) DO NOTHING;
    ELSIF (NEW.raw_user_meta_data->>'role') IN ('COMPTABLE', 'ACCOUNTANT') THEN
        INSERT INTO public.accountants (id, first_name, last_name, email, phone)
        VALUES (
            NEW.id,
            COALESCE(NEW.raw_user_meta_data->>'first_name', ''),
            COALESCE(NEW.raw_user_meta_data->>'last_name', ''),
            NEW.email,
            NEW.raw_user_meta_data->>'phone'
        )
        ON CONFLICT (id) DO NOTHING;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Suppression du trigger s'il existe déjà avant récréation
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ==============================================================================
-- Politiques RLS (Row Level Security)
-- ==============================================================================

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.parents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.accountants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.students ENABLE ROW LEVEL SECURITY;

-- Clean existing policies
DROP POLICY IF EXISTS "Les utilisateurs lisent leur propre profil ou les admins lisent tout" ON public.profiles;
DROP POLICY IF EXISTS "Lecture des parents par le parent lui-même ou admin/comptable" ON public.parents;
DROP POLICY IF EXISTS "Lecture des comptables par eux-mêmes ou admin" ON public.accountants;
DROP POLICY IF EXISTS "Lecture des élèves par leur parent ou admin/comptable" ON public.students;

-- Politiques pour PROFILES
CREATE POLICY "Les utilisateurs lisent leur propre profil ou les admins lisent tout"
    ON public.profiles FOR SELECT
    USING (
        auth.uid() = id OR 
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'ADMIN')
    );

-- Politiques pour PARENTS
CREATE POLICY "Lecture des parents par le parent lui-même ou admin/comptable"
    ON public.parents FOR SELECT
    USING (
        auth.uid() = id OR 
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('ADMIN', 'COMPTABLE'))
    );

-- Politiques pour ACCOUNTANTS
CREATE POLICY "Lecture des comptables par eux-mêmes ou admin"
    ON public.accountants FOR SELECT
    USING (
        auth.uid() = id OR 
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'ADMIN')
    );

-- Politiques pour STUDENTS
CREATE POLICY "Lecture des élèves par leur parent ou admin/comptable"
    ON public.students FOR SELECT
    USING (
        parent_id = auth.uid() OR 
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('ADMIN', 'COMPTABLE'))
    );
