import React, { useCallback } from 'react';
import { ClaudeChatWorkspace } from '../components/ClaudeChatWorkspace';
import { useStandaloneChatController } from './useStandaloneChatController';

/**
 * Standalone Chat surface.
 *
 * This app deliberately does not import the Workplace OS shell (`../App`),
 * graph/HUD state, or workspace navigation. It only composes the shared
 * Claude-style chat workspace with the chat controller, so `/chat.html` can be
 * developed, loaded, and troubleshot independently from Workplace OS at `/`.
 */
export const ChatApp: React.FC = () => {
  const chat = useStandaloneChatController();

  const openWorkplaceOS = useCallback(() => {
    window.location.assign('/');
  }, []);

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#f7f5ef] text-[#262624]">
      <ClaudeChatWorkspace {...chat} onClose={openWorkplaceOS} />
    </div>
  );
};
