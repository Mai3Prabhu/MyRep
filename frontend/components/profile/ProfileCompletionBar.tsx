"use client";

import React from "react";
import { Profile } from "@/types/profile";
import { KnowledgeStatus } from "@/types/knowledge";

interface Props {
  profile: Profile;
  knowledgeStatus: KnowledgeStatus | null;
}

export default function ProfileCompletionBar({ profile, knowledgeStatus }: Props) {
  let score = 0;
  const missingTips: string[] = [];

  // Name & headline: 20%
  if (profile.name) score += 10;
  if (profile.headline) score += 10;
  else missingTips.push("Add a professional headline");

  // About: 15%
  if (profile.about && profile.about.trim().length > 20) score += 15;
  else missingTips.push("Add a brief professional bio");

  // Skills: 15%
  if (Array.isArray(profile.skills) && profile.skills.length >= 3) score += 15;
  else missingTips.push("Add at least 3 skills");

  // Experience: 15%
  if (Array.isArray(profile.experience) && profile.experience.length >= 1) score += 15;
  else missingTips.push("Add your work experience");

  // Projects: 15%
  if (Array.isArray(profile.projects) && profile.projects.length >= 1) score += 15;
  else missingTips.push("Add at least one project");

  // Knowledge Documents: 20%
  if (knowledgeStatus && knowledgeStatus.indexed_documents >= 1) score += 20;
  else if (knowledgeStatus && knowledgeStatus.total_documents >= 1) score += 10;
  else missingTips.push("Upload and index a resume or document");

  score = Math.min(100, score);

  return (
    <div className="rounded-3xl border border-rep-lavender-200/80 bg-white p-5 sm:p-6 shadow-xs">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-slate-900">
              Profile Readiness
            </h3>
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                score >= 80
                  ? "bg-teal-50 text-rep-teal-700"
                  : score >= 50
                  ? "bg-amber-50 text-amber-700"
                  : "bg-purple-50 text-rep-lavender-700"
              }`}
            >
              {score}% ready
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {score >= 80
              ? "Your MyRep has strong grounded knowledge to represent your background."
              : "Complete the remaining items to help MyRep answer questions accurately."}
          </p>
        </div>

        {missingTips.length > 0 && (
          <div className="text-xs text-slate-400">
            <span className="font-medium text-slate-600">Next recommendation: </span>
            <span>{missingTips[0]}</span>
          </div>
        )}
      </div>

      {/* Progress Bar */}
      <div className="mt-4 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-gradient-to-r from-rep-teal-600 via-rep-lavender-500 to-rep-teal-500 transition-all duration-700 ease-out"
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );
}
