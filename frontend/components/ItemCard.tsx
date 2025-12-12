import React from 'react';

// Define Clip interface locally or import if available
interface Clip {
    url: string;
    timestamp: number;
    keywords: string;
    customText: string;
}

interface ItemCardProps {
    title: string;
    index: number;
    clips: Clip[];
    onUpdateTitle: (newTitle: string) => void;
    onAddClip: () => void;
    onRemoveClip: (clipIndex: number) => void;
    onUpdateClip: (clipIndex: number, field: string, value: any) => void;
    onRemoveItem: () => void;
}

const ItemCard: React.FC<ItemCardProps> = ({
    title,
    index,
    clips,
    onUpdateTitle,
    onAddClip,
    onRemoveClip,
    onUpdateClip,
    onRemoveItem
}) => {
    return (
        <div className="bg-gray-800 rounded-lg p-6 mb-6 border border-gray-700 shadow-xl">
            <div className="flex justify-between items-center mb-4 border-b border-gray-700 pb-4">
                <div className="flex items-center gap-4 flex-1">
                    <span className="text-2xl font-bold text-yellow-500">#{index + 1}</span>
                    <input
                        type="text"
                        value={title}
                        onChange={(e) => onUpdateTitle(e.target.value)}
                        placeholder="Item Title (e.g. Rolex)"
                        className="bg-gray-700 text-white px-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-500 flex-1 text-lg font-semibold"
                    />
                </div>
                <button
                    onClick={onRemoveItem}
                    className="ml-4 text-red-400 hover:text-red-300 transition-colors"
                >
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                </button>
            </div>

            <div className="space-y-4 pl-4 border-l-2 border-gray-700">
                {clips.map((clip, clipIndex) => (
                    <div key={clipIndex} className="bg-gray-900 rounded-lg p-4 border border-gray-700">
                        <div className="flex justify-between items-start mb-3">
                            <h4 className="text-sm font-medium text-gray-400">Clip {clipIndex + 1}</h4>
                            <button
                                onClick={() => onRemoveClip(clipIndex)}
                                className="text-red-400 hover:text-red-300 text-xs"
                            >
                                Remove Clip
                            </button>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label className="block text-xs text-gray-400 mb-1">YouTube URL</label>
                                <input
                                    type="text"
                                    value={clip.url}
                                    onChange={(e) => onUpdateClip(clipIndex, 'url', e.target.value)}
                                    placeholder="https://youtube.com/watch?v=..."
                                    className="w-full bg-gray-800 text-white px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none text-sm"
                                />
                            </div>

                            <div>
                                <label className="block text-xs text-gray-400 mb-1">Start Time (sec)</label>
                                <input
                                    type="number"
                                    value={clip.timestamp}
                                    onChange={(e) => onUpdateClip(clipIndex, 'timestamp', parseInt(e.target.value) || 0)}
                                    className="w-full bg-gray-800 text-white px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none text-sm"
                                />
                            </div>

                            <div className="md:col-span-2">
                                <label className="block text-xs text-gray-400 mb-1">Keywords for Summary</label>
                                <input
                                    type="text"
                                    value={clip.keywords}
                                    onChange={(e) => onUpdateClip(clipIndex, 'keywords', e.target.value)}
                                    placeholder="luxury watch, golden hands..."
                                    className="w-full bg-gray-800 text-white px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none text-sm"
                                />
                            </div>

                            <div className="md:col-span-2">
                                <label className="block text-xs text-gray-400 mb-1">Custom Subtitle (Overrides AI)</label>
                                <textarea
                                    value={clip.customText}
                                    onChange={(e) => onUpdateClip(clipIndex, 'customText', e.target.value)}
                                    placeholder="Enter custom subtitle text here..."
                                    rows={2}
                                    className="w-full bg-gray-800 text-white px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none text-sm resize-none"
                                />
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            <button
                onClick={onAddClip}
                className="mt-4 w-full py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-lg text-sm border-2 border-dashed border-gray-600 transition-colors"
            >
                + Add Clip to {title || "Item"}
            </button>
        </div>
    );
};

export default ItemCard;
