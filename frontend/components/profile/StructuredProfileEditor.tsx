"use client";

import React, { useState, useEffect } from "react";
import { Profile, ProfileUpdateInput } from "@/types/profile";
import { updateProfile } from "@/lib/api";

interface Props {
  profile: Profile;
  onProfileUpdated: (updated: Profile) => void;
  documentCount?: number;
  indexedCount?: number;
  knowledge?: React.ReactNode;
  visibility?: React.ReactNode;
}

interface ExperienceItem {
  role?: string;
  company?: string;
  start?: string;
  end?: string;
  description?: string;
}

interface ProjectItem {
  name?: string;
  description?: string;
  tech?: string[] | string;
  link?: string;
}

interface EducationItem {
  degree?: string;
  institution?: string;
  year?: string | number;
}

export default function StructuredProfileEditor({
  profile,
  onProfileUpdated,
  documentCount = 0,
  indexedCount = 0,
  knowledge,
  visibility,
}: Props) {
  // Basic info
  const [name, setName] = useState(profile.name || "");
  const [headline, setHeadline] = useState(profile.headline || "");
  const [about, setAbout] = useState(profile.about || "");

  // Skills
  const [skills, setSkills] = useState<string[]>(() => {
    if (!profile.skills || !Array.isArray(profile.skills)) return [];
    return profile.skills.map((s) => (typeof s === "string" ? s : s.name || JSON.stringify(s)));
  });
  const [newSkillInput, setNewSkillInput] = useState("");

  // Experience
  const [experience, setExperience] = useState<ExperienceItem[]>(() => {
    if (!profile.experience || !Array.isArray(profile.experience)) return [];
    return profile.experience.map((e) =>
      typeof e === "object" && e !== null ? e : { role: String(e) }
    );
  });
  const [editingExpIndex, setEditingExpIndex] = useState<number | null>(null);
  const [addingExp, setAddingExp] = useState(true);
  const [expForm, setExpForm] = useState<ExperienceItem>({});

  // Projects
  const [projects, setProjects] = useState<ProjectItem[]>(() => {
    if (!profile.projects || !Array.isArray(profile.projects)) return [];
    return profile.projects.map((p) =>
      typeof p === "object" && p !== null ? p : { name: String(p) }
    );
  });
  const [editingProjIndex, setEditingProjIndex] = useState<number | null>(null);
  const [projForm, setProjForm] = useState<ProjectItem>({});

  // Education
  const [education, setEducation] = useState<EducationItem[]>(() => {
    if (!profile.education || !Array.isArray(profile.education)) return [];
    return profile.education.map((ed) =>
      typeof ed === "object" && ed !== null ? ed : { degree: String(ed) }
    );
  });
  const [editingEduIndex, setEditingEduIndex] = useState<number | null>(null);
  const [eduForm, setEduForm] = useState<EducationItem>({});

  // Contact Preferences
  const [contactPrefs, setContactPrefs] = useState<{
    preferred?: string;
    allow_inquiries?: boolean;
    publicEmail?: string;
    publicLinkedin?: string;
    publicWebsite?: string;
  }>(() => {
    const cp = profile.contact_preferences || {};
    const pub = cp.public || {};
    return {
      preferred: cp.preferred || "email",
      allow_inquiries: cp.allow_inquiries ?? true,
      publicEmail: pub.email || "",
      publicLinkedin: pub.linkedin || "",
      publicWebsite: pub.website || "",
    };
  });

  // State
  const [openSection, setOpenSection] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  useEffect(() => {
    setName(profile.name || "");
    setHeadline(profile.headline || "");
    setAbout(profile.about || "");
    setSkills(
      Array.isArray(profile.skills)
        ? profile.skills.map((s) => (typeof s === "string" ? s : s.name || JSON.stringify(s)))
        : []
    );
    setExperience(
      Array.isArray(profile.experience)
        ? profile.experience.map((e) =>
            typeof e === "object" && e !== null ? e : { role: String(e) }
          )
        : []
    );
    setProjects(
      Array.isArray(profile.projects)
        ? profile.projects.map((p) =>
            typeof p === "object" && p !== null ? p : { name: String(p) }
          )
        : []
    );
    setEducation(
      Array.isArray(profile.education)
        ? profile.education.map((ed) =>
            typeof ed === "object" && ed !== null ? ed : { degree: String(ed) }
          )
        : []
    );
    const cp = profile.contact_preferences || {};
    const pub = cp.public || {};
    setContactPrefs({
      preferred: cp.preferred || "email",
      allow_inquiries: cp.allow_inquiries ?? true,
      publicEmail: pub.email || "",
      publicLinkedin: pub.linkedin || "",
      publicWebsite: pub.website || "",
    });
  }, [profile]);

  // Skill management
  const handleAddSkill = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newSkillInput.trim();
    if (trimmed && !skills.includes(trimmed)) {
      setSkills([...skills, trimmed]);
      setNewSkillInput("");
    }
  };

  const handleRemoveSkill = (skillToRemove: string) => {
    setSkills(skills.filter((s) => s !== skillToRemove));
  };

  // Experience management
  const handleSaveExp = () => {
    if (!expForm.role?.trim() && !expForm.company?.trim()) return false;
    if (editingExpIndex !== null && editingExpIndex >= 0) {
      const updated = [...experience];
      updated[editingExpIndex] = expForm;
      setExperience(updated);
    } else {
      setExperience([...experience, expForm]);
    }
    setEditingExpIndex(null);
    setExpForm({});
    return true;
  };

  const handleDeleteExp = (index: number) => {
    setExperience(experience.filter((_, i) => i !== index));
    if (editingExpIndex === index) {
      setEditingExpIndex(null);
      setExpForm({});
    } else if (editingExpIndex !== null && editingExpIndex > index) {
      setEditingExpIndex(editingExpIndex - 1);
    }
  };

  // Project management
  const handleSaveProj = () => {
    if (!projForm.name?.trim()) return;
    if (editingProjIndex !== null && editingProjIndex >= 0) {
      const updated = [...projects];
      updated[editingProjIndex] = projForm;
      setProjects(updated);
    } else {
      setProjects([...projects, projForm]);
    }
    setEditingProjIndex(null);
    setProjForm({});
  };

  const handleDeleteProj = (index: number) => {
    setProjects(projects.filter((_, i) => i !== index));
  };

  // Education management
  const handleSaveEdu = () => {
    if (!eduForm.degree?.trim() && !eduForm.institution?.trim()) return;
    if (editingEduIndex !== null && editingEduIndex >= 0) {
      const updated = [...education];
      updated[editingEduIndex] = eduForm;
      setEducation(updated);
    } else {
      setEducation([...education, eduForm]);
    }
    setEditingEduIndex(null);
    setEduForm({});
  };

  const handleDeleteEdu = (index: number) => {
    setEducation(education.filter((_, i) => i !== index));
  };

  // Full Save Handler
  const handleSaveAll = async () => {
    setSaving(true);
    setSaveSuccess(null);
    setSaveError(null);

    const contactPayload: Record<string, any> = {
      preferred: contactPrefs.preferred,
      allow_inquiries: contactPrefs.allow_inquiries,
      public: {
        ...(contactPrefs.publicEmail ? { email: contactPrefs.publicEmail } : {}),
        ...(contactPrefs.publicLinkedin ? { linkedin: contactPrefs.publicLinkedin } : {}),
        ...(contactPrefs.publicWebsite ? { website: contactPrefs.publicWebsite } : {}),
      },
    };

    const payload: ProfileUpdateInput = {
      name: name.trim(),
      headline: headline.trim() || null,
      about: about.trim() || null,
      skills: skills,
      experience: experience,
      projects: projects,
      education: education,
      contact_preferences: contactPayload,
    };

    try {
      const updated = await updateProfile(profile.id, payload);
      onProfileUpdated(updated);
      setSaveSuccess("Changes saved successfully.");
      setTimeout(() => setSaveSuccess(null), 4000);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Failed to save profile changes.");
    } finally {
      setSaving(false);
    }
  };

  const contactReady = Boolean(
    contactPrefs.publicEmail || contactPrefs.publicLinkedin || contactPrefs.publicWebsite
  );
  const checks = [
    { label: "Profile", done: Boolean(name.trim() && (headline.trim() || about.trim())) },
    { label: "Skills", done: skills.length > 0 },
    { label: "Experience", done: experience.length > 0 },
    { label: "Knowledge", done: documentCount > 0 },
    { label: "Projects", done: projects.length > 0 },
    { label: "Contact", done: contactReady },
  ];
  const readyPct = Math.round((checks.filter((item) => item.done).length / checks.length) * 100);

  const openStory = (id: string) => {
    setOpenSection(openSection === id ? "" : id);
  };

  return (
    <div className="space-y-10">
      {saveError && (
        <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
          {saveError}
        </p>
      )}

      <div className="grid items-start gap-8 xl:grid-cols-[240px_minmax(0,1fr)_250px]">
        <div className="relative mx-auto w-full max-w-[240px] pt-2 text-center xl:mx-0 xl:text-left">
          <img
            src="/images/rep-chosen.png?v=2"
            alt="Rep"
            className="mx-auto h-auto w-[200px] object-contain xl:mx-0"
          />
          <div className="relative mx-auto mt-1 max-w-[210px] rounded-2xl bg-white/80 px-4 py-3 text-left shadow-[0_10px_30px_-18px_rgba(80,40,70,0.35)]">
            <p className="font-handwriting text-[1.65rem] leading-none text-[#6D5A86]">Hi, I&apos;m Rep.</p>
            <p className="mt-2 text-sm leading-relaxed text-[#5C5666]">
              Let&apos;s build your AI representative together.
            </p>
          </div>
        </div>

        <section className="rounded-[22px] border border-[#F0E6DE] bg-white px-6 py-6 shadow-[0_18px_40px_-28px_rgba(70,36,58,0.35)] sm:px-7 sm:py-7">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="font-display text-[1.7rem] leading-none text-[#16161D]">Your identity</h2>
              <p className="mt-2 text-sm text-[#6B6574]">This is how your Rep will introduce you.</p>
            </div>
            {saveSuccess && <p className="text-sm text-[#0F766E]">Saved</p>}
          </div>

          <div className="mt-6 grid gap-5 sm:grid-cols-2">
            <label className="block text-sm text-[#6B6574]">
              Full name
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className={fieldClass}
              />
            </label>
            <label className="block text-sm text-[#6B6574]">
              Professional headline
              <input
                type="text"
                value={headline}
                onChange={(e) => setHeadline(e.target.value)}
                placeholder="AI Engineer & Full Stack Developer"
                className={fieldClass}
              />
            </label>
          </div>

          <label className="mt-5 block text-sm text-[#6B6574]">
            About you
            <textarea
              rows={4}
              value={about}
              onChange={(e) => setAbout(e.target.value)}
              placeholder="Tell your Rep what you do, what you care about, and the work you've done."
              className={fieldClass}
            />
          </label>
        </section>

        <aside className="rounded-[22px] border border-[#F0E6DE] bg-white px-5 py-5 shadow-[0_18px_40px_-28px_rgba(70,36,58,0.28)]">
          <p className="text-sm text-[#3D3A45]">
            Your Rep is <span className="font-medium text-[#16161D]">{readyPct}% ready</span>
          </p>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[#F3E8FF]">
            <div className="h-full rounded-full bg-[#9B4D86]" style={{ width: `${readyPct}%` }} />
          </div>
          <ul className="mt-4 grid grid-cols-2 gap-x-3 gap-y-2.5">
            {checks.map((item) => (
              <li key={item.label} className="flex items-center gap-2 text-sm text-[#3D3A45]">
                <span
                  className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] ${
                    item.done ? "bg-[#E7F6F1] text-[#0F766E]" : "border border-[#E0D8D0]"
                  }`}
                  aria-hidden="true"
                >
                  {item.done ? "✓" : ""}
                </span>
                {item.label}
              </li>
            ))}
          </ul>
          {indexedCount > 0 && (
            <p className="mt-4 text-xs text-[#8A8494]">{indexedCount} document{indexedCount === 1 ? "" : "s"} ready</p>
          )}
        </aside>
      </div>

      <section>
        <h2 className="font-display text-3xl text-[#16161D]">Your story</h2>
        <p className="mt-2 text-sm text-[#6B6574]">
          Add your professional experience, projects, skills and education.
        </p>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StoryTile
            title="Experience"
            body="Where you've worked"
            meta={experience.length === 1 ? "1 experience" : `${experience.length} experiences`}
            active={openSection === "experience"}
            tint="bg-[#FBF3DC] text-[#C4922A]"
            icon="case"
            onClick={() => openStory("experience")}
          />
          <StoryTile
            title="Projects"
            body="Your work and things you've built"
            meta={projects.length === 1 ? "1 project" : `${projects.length} projects`}
            active={openSection === "projects"}
            tint="bg-[#F3E8FF] text-[#8B6AAE]"
            icon="spark"
            onClick={() => openStory("projects")}
          />
          <StoryTile
            title="Skills"
            body="Technologies and tools you use"
            meta={skills.length === 1 ? "1 skill" : `${skills.length} skills`}
            active={openSection === "skills"}
            tint="bg-[#E7F6F1] text-[#0F766E]"
            icon="bolt"
            onClick={() => openStory("skills")}
          />
          <StoryTile
            title="Education"
            body="Your academic background"
            meta={education.length === 1 ? "1 entry" : `${education.length} entries`}
            active={openSection === "education"}
            tint="bg-[#F4EEFF] text-[#7C6BB0]"
            icon="cap"
            onClick={() => openStory("education")}
          />
        </div>

        {openSection === "skills" && (
          <div className="mt-4 rounded-[22px] border border-[#F0E6DE] bg-white p-5 sm:p-6">
            <h3 className="font-display text-2xl">Skills</h3>
            <p className="mt-1 text-sm text-[#6B6574]">What you work with.</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {skills.map((skill) => (
                <span
                  key={skill}
                  className="inline-flex items-center gap-2 rounded-full bg-[#F7F1FA] px-3 py-1.5 text-sm text-[#3D3A45]"
                >
                  {skill}
                  <button
                    type="button"
                    onClick={() => handleRemoveSkill(skill)}
                    className="text-[#8A8494] hover:text-red-600"
                    aria-label={`Remove ${skill}`}
                  >
                    ×
                  </button>
                </span>
              ))}
              {skills.length === 0 && <p className="text-sm text-[#8A8494]">No skills yet.</p>}
            </div>
            <form onSubmit={handleAddSkill} className="mt-4 flex max-w-md gap-2">
              <input
                type="text"
                placeholder="LangGraph, PyTorch, Docker"
                value={newSkillInput}
                onChange={(e) => setNewSkillInput(e.target.value)}
                className={`${fieldClass} mt-0`}
              />
              <button type="submit" className="shrink-0 rounded-full bg-[#16161D] px-4 text-sm text-white">
                Add
              </button>
            </form>
          </div>
        )}

        {openSection === "projects" && (
          <div className="mt-4 rounded-[22px] border border-[#F0E6DE] bg-white p-5 sm:p-6">
            <h3 className="font-display text-2xl">Projects</h3>
            <p className="mt-1 text-sm text-[#6B6574]">Your work speaks for you.</p>
            <div className="mt-4 space-y-3">
              {projects.map((proj, idx) => {
                const techList = Array.isArray(proj.tech)
                  ? proj.tech
                  : typeof proj.tech === "string"
                  ? proj.tech.split(",").map((t) => t.trim()).filter(Boolean)
                  : [];
                return (
                  <article key={idx} className="rounded-2xl border border-[#F3EBE3] px-4 py-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h4 className="text-base text-[#16161D]">{proj.name || "Untitled project"}</h4>
                        {proj.description && (
                          <p className="mt-1 text-sm leading-relaxed text-[#5C5666]">{proj.description}</p>
                        )}
                      </div>
                      <div className="flex shrink-0 gap-3 text-sm">
                        <button
                          type="button"
                          onClick={() => {
                            setEditingProjIndex(idx);
                            setProjForm(proj);
                          }}
                          className="text-[#5C5666] hover:text-[#16161D]"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteProj(idx)}
                          className="text-[#A45B68] hover:text-red-700"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                    {techList.length > 0 && (
                      <p className="mt-3 text-sm text-[#8A8494]">{techList.join(" · ")}</p>
                    )}
                  </article>
                );
              })}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <input
                type="text"
                placeholder="Project name"
                value={projForm.name || ""}
                onChange={(e) => setProjForm({ ...projForm, name: e.target.value })}
                className={fieldClass}
              />
              <input
                type="text"
                placeholder="Technologies, separated by commas"
                value={Array.isArray(projForm.tech) ? projForm.tech.join(", ") : projForm.tech || ""}
                onChange={(e) =>
                  setProjForm({
                    ...projForm,
                    tech: e.target.value.split(",").map((s) => s.trim()),
                  })
                }
                className={fieldClass}
              />
              <textarea
                rows={2}
                placeholder="What it is and why it matters"
                value={projForm.description || ""}
                onChange={(e) => setProjForm({ ...projForm, description: e.target.value })}
                className={`${fieldClass} sm:col-span-2`}
              />
            </div>
            <div className="mt-3 flex justify-end gap-2">
              {editingProjIndex !== null && (
                <button
                  type="button"
                  onClick={() => {
                    setEditingProjIndex(null);
                    setProjForm({});
                  }}
                  className="rounded-full px-4 py-2 text-sm text-[#5C5666]"
                >
                  Cancel
                </button>
              )}
              <button
                type="button"
                onClick={handleSaveProj}
                className="rounded-full bg-[#16161D] px-4 py-2 text-sm text-white"
              >
                {editingProjIndex !== null ? "Update project" : "Add project"}
              </button>
            </div>
          </div>
        )}

        {openSection === "experience" && (
          <div className="mt-4 rounded-[22px] border border-[#F0E6DE] bg-white p-5 sm:p-6">
            <h3 className="font-display text-2xl">Experience</h3>
            <p className="mt-1 text-sm text-[#6B6574]">Where you&apos;ve worked.</p>
            <div className="mt-4 space-y-3">
              {experience.map((exp, idx) => (
                <article key={idx} className="rounded-2xl border border-[#F3EBE3] px-4 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h4 className="text-base text-[#16161D]">
                        {exp.role || "Role"}
                        {exp.company ? ` at ${exp.company}` : ""}
                      </h4>
                      <p className="mt-1 text-sm text-[#8A8494]">
                        {[exp.start, exp.end].filter(Boolean).join(" — ") || "Dates not specified"}
                      </p>
                      {exp.description && (
                        <p className="mt-2 text-sm leading-relaxed text-[#5C5666]">{exp.description}</p>
                      )}
                    </div>
                    <div className="flex shrink-0 gap-2 text-sm">
                      <button
                        type="button"
                        onClick={() => {
                          setAddingExp(false);
                          setEditingExpIndex(idx);
                          setExpForm(exp);
                        }}
                        className="rounded-full border border-[#E7DDD4] px-3 py-1 text-[#16161D] hover:bg-[#FBF8F4]"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteExp(idx)}
                        className="rounded-full px-3 py-1 text-[#A45B68] hover:text-red-700"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
            {(addingExp || editingExpIndex !== null || experience.length === 0) && (
            <div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <input
                type="text"
                placeholder="Role"
                value={expForm.role || ""}
                onChange={(e) => setExpForm({ ...expForm, role: e.target.value })}
                className={fieldClass}
              />
              <input
                type="text"
                placeholder="Company"
                value={expForm.company || ""}
                onChange={(e) => setExpForm({ ...expForm, company: e.target.value })}
                className={fieldClass}
              />
              <input
                type="text"
                placeholder="Start"
                value={expForm.start || ""}
                onChange={(e) => setExpForm({ ...expForm, start: e.target.value })}
                className={fieldClass}
              />
              <div>
                <input
                  type="text"
                  placeholder="End"
                  value={expForm.end || ""}
                  disabled={/^(present|current)$/i.test((expForm.end || "").trim())}
                  onChange={(e) => setExpForm({ ...expForm, end: e.target.value })}
                  className={`${fieldClass} disabled:bg-[#F7F3EE] disabled:text-[#6B6574]`}
                />
                <label className="mt-2 flex items-center gap-2 text-sm text-[#5C5666]">
                  <input
                    type="checkbox"
                    checked={/^(present|current)$/i.test((expForm.end || "").trim())}
                    onChange={(e) =>
                      setExpForm({
                        ...expForm,
                        end: e.target.checked ? "Present" : "",
                      })
                    }
                    className="h-4 w-4 accent-[#16161D]"
                  />
                  I currently work here
                </label>
              </div>
              <textarea
                rows={2}
                placeholder="What you did"
                value={expForm.description || ""}
                onChange={(e) => setExpForm({ ...expForm, description: e.target.value })}
                className={`${fieldClass} sm:col-span-2`}
              />
            </div>
            <div className="mt-3 flex items-center justify-end gap-2">
              {editingExpIndex !== null && (
                <button
                  type="button"
                  onClick={() => {
                    setEditingExpIndex(null);
                    setExpForm({});
                    setAddingExp(false);
                  }}
                  className="rounded-full px-4 py-2 text-sm text-[#5C5666]"
                >
                  Cancel
                </button>
              )}
              <button
                type="button"
                aria-label="Add another experience"
                onClick={() => {
                  handleSaveExp();
                  setAddingExp(true);
                }}
                className="flex h-10 w-10 items-center justify-center rounded-full border border-[#E7DDD4] text-lg leading-none text-[#16161D] hover:bg-[#FBF8F4]"
              >
                +
              </button>
              <button
                type="button"
                onClick={() => {
                  if (handleSaveExp()) setAddingExp(false);
                }}
                className="rounded-full bg-[#16161D] px-4 py-2 text-sm text-white"
              >
                Save
              </button>
            </div>
            </div>
            )}
            {!(addingExp || editingExpIndex !== null || experience.length === 0) && (
              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  aria-label="Add another experience"
                  onClick={() => {
                    setEditingExpIndex(null);
                    setExpForm({});
                    setAddingExp(true);
                  }}
                  className="flex h-10 w-10 items-center justify-center rounded-full border border-[#E7DDD4] text-lg leading-none text-[#16161D] hover:bg-[#FBF8F4]"
                >
                  +
                </button>
              </div>
            )}
          </div>
        )}

        {openSection === "education" && (
          <div className="mt-4 rounded-[22px] border border-[#F0E6DE] bg-white p-5 sm:p-6">
            <h3 className="font-display text-2xl">Education</h3>
            <p className="mt-1 text-sm text-[#6B6574]">Your academic background.</p>
            <div className="mt-4 space-y-3">
              {education.map((edu, idx) => (
                <article key={idx} className="flex items-start justify-between gap-3 rounded-2xl border border-[#F3EBE3] px-4 py-4">
                  <div>
                    <h4 className="text-base text-[#16161D]">{edu.degree || "Degree"}</h4>
                    <p className="mt-1 text-sm text-[#8A8494]">
                      {[edu.institution, edu.year].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-3 text-sm">
                    <button
                      type="button"
                      onClick={() => {
                        setEditingEduIndex(idx);
                        setEduForm(edu);
                      }}
                      className="text-[#5C5666] hover:text-[#16161D]"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeleteEdu(idx)}
                      className="text-[#A45B68] hover:text-red-700"
                    >
                      Remove
                    </button>
                  </div>
                </article>
              ))}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <input
                type="text"
                placeholder="Degree"
                value={eduForm.degree || ""}
                onChange={(e) => setEduForm({ ...eduForm, degree: e.target.value })}
                className={fieldClass}
              />
              <input
                type="text"
                placeholder="Institution"
                value={eduForm.institution || ""}
                onChange={(e) => setEduForm({ ...eduForm, institution: e.target.value })}
                className={fieldClass}
              />
              <input
                type="text"
                placeholder="Year"
                value={eduForm.year ?? ""}
                onChange={(e) => setEduForm({ ...eduForm, year: e.target.value })}
                className={fieldClass}
              />
            </div>
            <div className="mt-3 flex justify-end gap-2">
              {editingEduIndex !== null && (
                <button
                  type="button"
                  onClick={() => {
                    setEditingEduIndex(null);
                    setEduForm({});
                  }}
                  className="rounded-full px-4 py-2 text-sm text-[#5C5666]"
                >
                  Cancel
                </button>
              )}
              <button
                type="button"
                onClick={handleSaveEdu}
                className="rounded-full bg-[#16161D] px-4 py-2 text-sm text-white"
              >
                {editingEduIndex !== null ? "Update education" : "Add education"}
              </button>
            </div>
          </div>
        )}
      </section>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)]">
        <div>{knowledge}</div>
        <div className="space-y-4">
          {visibility}
          <section className="rounded-[22px] border border-[#F0E6DE] bg-white px-5 py-5">
            <button
              type="button"
              onClick={() => openStory("contact")}
              className="flex w-full items-center justify-between text-left"
            >
              <span>
                <span className="block text-sm font-medium text-[#16161D]">Contact preferences</span>
                <span className="mt-1 block text-sm text-[#6B6574]">
                  Email, LinkedIn or other ways for people to reach you.
                </span>
              </span>
              <span className="text-[#8A8494]" aria-hidden="true">
                {openSection === "contact" ? "–" : "+"}
              </span>
            </button>
            {openSection === "contact" && (
              <div className="mt-4 space-y-3 border-t border-[#F3EBE3] pt-4">
                <label className="flex items-center justify-between gap-3 text-sm text-[#3D3A45]">
                  Allow people to leave an inquiry
                  <input
                    type="checkbox"
                    checked={contactPrefs.allow_inquiries ?? true}
                    onChange={(e) =>
                      setContactPrefs({ ...contactPrefs, allow_inquiries: e.target.checked })
                    }
                    className="h-4 w-4 accent-[#16161D]"
                  />
                </label>
                <label className="block text-sm text-[#6B6574]">
                  Email
                  <input
                    type="email"
                    placeholder="you@example.com"
                    value={contactPrefs.publicEmail}
                    onChange={(e) => setContactPrefs({ ...contactPrefs, publicEmail: e.target.value })}
                    className={fieldClass}
                  />
                </label>
                <label className="block text-sm text-[#6B6574]">
                  LinkedIn
                  <input
                    type="url"
                    placeholder="https://linkedin.com/in/..."
                    value={contactPrefs.publicLinkedin}
                    onChange={(e) =>
                      setContactPrefs({ ...contactPrefs, publicLinkedin: e.target.value })
                    }
                    className={fieldClass}
                  />
                </label>
                <label className="block text-sm text-[#6B6574]">
                  Website
                  <input
                    type="url"
                    placeholder="https://example.com"
                    value={contactPrefs.publicWebsite}
                    onChange={(e) =>
                      setContactPrefs({ ...contactPrefs, publicWebsite: e.target.value })
                    }
                    className={fieldClass}
                  />
                </label>
              </div>
            )}
          </section>
        </div>
      </div>

      <div className="sticky bottom-4 z-20 flex justify-end">
        <button
          type="button"
          onClick={handleSaveAll}
          disabled={saving}
          className="rounded-full border border-[#E8E0D6] bg-white/95 px-5 py-2.5 text-sm text-[#16161D] shadow-[0_10px_30px_-18px_rgba(40,20,30,0.45)] backdrop-blur disabled:opacity-50"
        >
          {saving ? "Saving…" : saveSuccess ? "Changes saved" : "Save changes"}
        </button>
      </div>
    </div>
  );
}

const fieldClass =
  "mt-2 w-full rounded-2xl border border-[#E7E0D6] bg-[#FFFCFA] px-4 py-3 text-sm text-[#16161D] outline-none transition placeholder:text-[#B0A8B4] focus:border-[#D4B8D8] focus:ring-4 focus:ring-[#E7D4F5]/70";

function StoryTile({
  title,
  body,
  meta,
  active,
  tint,
  icon,
  onClick,
}: {
  title: string;
  body: string;
  meta: string;
  active: boolean;
  tint: string;
  icon: "case" | "spark" | "bolt" | "cap";
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-[20px] border bg-white px-4 py-4 text-left transition ${
        active ? "border-[#D4B8D8] shadow-[0_12px_30px_-20px_rgba(80,40,70,0.45)]" : "border-[#F0E6DE] hover:border-[#E4D4C8]"
      }`}
    >
      <span className={`flex h-9 w-9 items-center justify-center rounded-full ${tint}`}>
        <TileIcon name={icon} />
      </span>
      <span className="mt-3 block text-sm font-medium text-[#16161D]">{title}</span>
      <span className="mt-1 block text-sm leading-snug text-[#6B6574]">{body}</span>
      <span className="mt-3 block text-xs text-[#8A8494]">{meta}</span>
    </button>
  );
}

function TileIcon({ name }: { name: "case" | "spark" | "bolt" | "cap" }) {
  if (name === "spark") {
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 3.2 14.1 8.7l5.9.5-4.5 3.7 1.4 5.7L12 15.8 7.1 18.6l1.4-5.7L4 9.2l5.9-.5L12 3.2Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    );
  }
  if (name === "bolt") {
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M13 3 5.5 13.5H12L11 21l7.5-10.5H12L13 3Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    );
  }
  if (name === "cap") {
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M3 10 12 6l9 4-9 4-9-4Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M7 12.2V16c1.4 1.3 3.1 2 5 2s3.6-.7 5-2v-3.8" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    );
  }
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="7" width="17" height="12" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 7V5.8A1.8 1.8 0 0 1 9.8 4h4.4A1.8 1.8 0 0 1 16 5.8V7" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}
