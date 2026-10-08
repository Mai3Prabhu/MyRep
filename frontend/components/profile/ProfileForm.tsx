"use client";

import { useState, useEffect } from "react";
import { Profile, ProfileUpdateInput } from "@/types/profile";
import { updateProfile } from "@/lib/api";

interface ProfileFormProps {
  profile: Profile;
  onProfileUpdated: (updated: Profile) => void;
}

export function ProfileForm({ profile, onProfileUpdated }: ProfileFormProps) {
  const [name, setName] = useState(profile.name);
  const [headline, setHeadline] = useState(profile.headline || "");
  const [about, setAbout] = useState(profile.about || "");
  const [skillsText, setSkillsText] = useState(
    profile.skills ? JSON.stringify(profile.skills, null, 2) : "[]"
  );
  const [experienceText, setExperienceText] = useState(
    profile.experience ? JSON.stringify(profile.experience, null, 2) : "[]"
  );
  const [projectsText, setProjectsText] = useState(
    profile.projects ? JSON.stringify(profile.projects, null, 2) : "[]"
  );
  const [educationText, setEducationText] = useState(
    profile.education ? JSON.stringify(profile.education, null, 2) : "[]"
  );
  const [contactText, setContactText] = useState(
    profile.contact_preferences
      ? JSON.stringify(profile.contact_preferences, null, 2)
      : "{}"
  );

  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    setName(profile.name);
    setHeadline(profile.headline || "");
    setAbout(profile.about || "");
    setSkillsText(
      profile.skills ? JSON.stringify(profile.skills, null, 2) : "[]"
    );
    setExperienceText(
      profile.experience ? JSON.stringify(profile.experience, null, 2) : "[]"
    );
    setProjectsText(
      profile.projects ? JSON.stringify(profile.projects, null, 2) : "[]"
    );
    setEducationText(
      profile.education ? JSON.stringify(profile.education, null, 2) : "[]"
    );
    setContactText(
      profile.contact_preferences
        ? JSON.stringify(profile.contact_preferences, null, 2)
        : "{}"
    );
    setSaveSuccess(null);
    setSaveError(null);
  }, [profile]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveSuccess(null);
    setSaveError(null);

    // Validate JSON fields before sending
    let parsedSkills: any[] | null = null;
    let parsedExperience: any[] | null = null;
    let parsedProjects: any[] | null = null;
    let parsedEducation: any[] | null = null;
    let parsedContact: Record<string, any> | null = null;

    try {
      if (skillsText.trim()) {
        parsedSkills = JSON.parse(skillsText);
        if (!Array.isArray(parsedSkills)) {
          throw new Error("Skills must be a valid JSON array.");
        }
      }
    } catch (err: any) {
      setSaveError(`Skills JSON error: ${err.message}`);
      setSaving(false);
      return;
    }

    try {
      if (experienceText.trim()) {
        parsedExperience = JSON.parse(experienceText);
        if (!Array.isArray(parsedExperience)) {
          throw new Error("Experience must be a valid JSON array.");
        }
      }
    } catch (err: any) {
      setSaveError(`Experience JSON error: ${err.message}`);
      setSaving(false);
      return;
    }

    try {
      if (projectsText.trim()) {
        parsedProjects = JSON.parse(projectsText);
        if (!Array.isArray(parsedProjects)) {
          throw new Error("Projects must be a valid JSON array.");
        }
      }
    } catch (err: any) {
      setSaveError(`Projects JSON error: ${err.message}`);
      setSaving(false);
      return;
    }

    try {
      if (educationText.trim()) {
        parsedEducation = JSON.parse(educationText);
        if (!Array.isArray(parsedEducation)) {
          throw new Error("Education must be a valid JSON array.");
        }
      }
    } catch (err: any) {
      setSaveError(`Education JSON error: ${err.message}`);
      setSaving(false);
      return;
    }

    try {
      if (contactText.trim()) {
        parsedContact = JSON.parse(contactText);
        if (
          typeof parsedContact !== "object" ||
          Array.isArray(parsedContact)
        ) {
          throw new Error(
            "Contact preferences must be a valid JSON object."
          );
        }
      }
    } catch (err: any) {
      setSaveError(`Contact preferences JSON error: ${err.message}`);
      setSaving(false);
      return;
    }

    const payload: ProfileUpdateInput = {
      name: name.trim(),
      headline: headline.trim() || null,
      about: about.trim() || null,
      skills: parsedSkills,
      experience: parsedExperience,
      projects: parsedProjects,
      education: parsedEducation,
      contact_preferences: parsedContact,
    };

    try {
      const updated = await updateProfile(profile.id, payload);
      onProfileUpdated(updated);
      setSaveSuccess("Profile saved successfully.");
    } catch (err: any) {
      setSaveError(err.message || "Failed to update profile.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="flex items-center justify-between border-b border-slate-200 pb-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">
            Profile Details
          </h2>
          <p className="text-xs text-slate-500">
            ID: <span className="font-mono text-slate-700">{profile.id}</span>
          </p>
        </div>
        <div className="text-right text-xs text-slate-400">
          <div>
            Created: {new Date(profile.created_at).toLocaleDateString()}
          </div>
          <div>
            Updated: {new Date(profile.updated_at).toLocaleTimeString()}
          </div>
        </div>
      </div>

      {saveSuccess && (
        <div className="rounded border border-green-200 bg-green-50 p-3 text-sm text-green-700">
          {saveSuccess}
        </div>
      )}

      {saveError && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {saveError}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="block text-sm font-medium text-slate-700">
            Full Name *
          </label>
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700">
            Headline
          </label>
          <input
            type="text"
            value={headline}
            onChange={(e) => setHeadline(e.target.value)}
            placeholder="e.g. Senior Software Engineer"
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700">
          About
        </label>
        <textarea
          rows={3}
          value={about}
          onChange={(e) => setAbout(e.target.value)}
          placeholder="Brief professional summary..."
          className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        />
      </div>

      {/* JSON structured fields */}
      <div className="space-y-4 pt-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          Structured Knowledge Fields (JSON)
        </h3>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div>
            <label className="block text-xs font-medium text-slate-600">
              Skills (JSON array)
            </label>
            <textarea
              rows={4}
              value={skillsText}
              onChange={(e) => setSkillsText(e.target.value)}
              className="mt-1 w-full font-mono text-xs rounded border border-slate-300 p-2 focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600">
              Contact Preferences (JSON object)
            </label>
            <p className="mt-0.5 text-[11px] text-slate-400">
              Only methods under a nested <code>public</code> object
              (email, linkedin, website) are shown to visitors. Other keys stay private.
            </p>
            <textarea
              rows={4}
              value={contactText}
              onChange={(e) => setContactText(e.target.value)}
              className="mt-1 w-full font-mono text-xs rounded border border-slate-300 p-2 focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div>
            <label className="block text-xs font-medium text-slate-600">
              Experience (JSON array)
            </label>
            <textarea
              rows={6}
              value={experienceText}
              onChange={(e) => setExperienceText(e.target.value)}
              className="mt-1 w-full font-mono text-xs rounded border border-slate-300 p-2 focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600">
              Projects (JSON array)
            </label>
            <textarea
              rows={6}
              value={projectsText}
              onChange={(e) => setProjectsText(e.target.value)}
              className="mt-1 w-full font-mono text-xs rounded border border-slate-300 p-2 focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600">
              Education (JSON array)
            </label>
            <textarea
              rows={6}
              value={educationText}
              onChange={(e) => setEducationText(e.target.value)}
              className="mt-1 w-full font-mono text-xs rounded border border-slate-300 p-2 focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>
      </div>

      <div className="flex justify-end pt-4">
        <button
          type="submit"
          disabled={saving}
          className="rounded bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? "Saving Changes..." : "Save Profile"}
        </button>
      </div>
    </form>
  );
}
